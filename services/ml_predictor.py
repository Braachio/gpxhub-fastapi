import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import joblib
import numpy as np


class EnsemblePredictor:
    """
    Lazy-loaded ensemble predictor that wraps the saved scikit-learn/XGBoost/LightGBM models.
    """

    def __init__(self, config_path: Path, mode: str):
        self.config_path = config_path
        self.mode = mode
        self.config = self._load_config(config_path)
        self.feature_names: List[str] = self.config["features"]
        self.models = self._load_models(config_path.parent, self.config["models"])
        self.model_version = self.config.get("timestamp")
        self.feature_importances = self._aggregate_feature_importances()

    @staticmethod
    def _load_config(path: Path) -> Dict:
        if not path.exists():
            raise FileNotFoundError(f"Ensemble config not found: {path}")
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _load_models(base_dir: Path, model_entries: List[Dict]) -> List[Dict]:
        loaded = []
        for entry in model_entries:
            rel_path = entry.get("model_path")
            model_path = (base_dir / rel_path).resolve()
            if not model_path.exists():
                raise FileNotFoundError(f"Model file not found: {model_path}")
            model = joblib.load(model_path)
            loaded.append(
                {
                    "name": entry.get("name"),
                    "weight": float(entry.get("weight", 0)),
                    "r2": float(entry.get("r2", 0)),
                    "model": model,
                }
            )
        weight_sum = sum(m["weight"] for m in loaded)
        if weight_sum == 0:
            raise ValueError("Model weights sum to zero; invalid ensemble configuration.")
        # Normalize weights to ensure they add up to 1
        for item in loaded:
            item["weight"] /= weight_sum
        return loaded

    @staticmethod
    def _extract_model_importances(model) -> Optional[np.ndarray]:
        if hasattr(model, "feature_importances_"):
            importance = getattr(model, "feature_importances_")
            return np.asarray(importance, dtype=float)
        if hasattr(model, "coef_"):
            coef = np.asarray(getattr(model, "coef_"), dtype=float)
            if coef.ndim > 1:
                coef = coef[0]
            return np.abs(coef)
        return None

    def _aggregate_feature_importances(self) -> Optional[Dict[str, float]]:
        importances = np.zeros(len(self.feature_names), dtype=float)
        has_valid = False

        for entry in self.models:
            weight = entry["weight"]
            model = entry["model"]
            raw_importance = self._extract_model_importances(model)
            if raw_importance is None:
                continue
            raw_importance = np.asarray(raw_importance, dtype=float)
            if raw_importance.shape[0] != len(self.feature_names):
                continue
            importances += weight * raw_importance
            has_valid = True

        if not has_valid:
            return None

        total = importances.sum()
        if total > 0:
            importances = importances / total

        return dict(zip(self.feature_names, importances.tolist()))

    def vectorize_features(
        self, feature_payload: Dict[str, Optional[float]]
    ) -> Tuple[np.ndarray, int]:
        """
        Convert dictionary payload into ordered numpy vector expected by the ensemble.
        Returns (vector, missing_count)
        """
        vector = []
        missing_count = 0

        def normalize_category_value(value: Optional[float]) -> Optional[str]:
            if value is None:
                return None
            if isinstance(value, str):
                return value
            try:
                return str(int(value))
            except Exception:
                return str(value)

        series_id = normalize_category_value(
            feature_payload.get("series_id") or feature_payload.get("seriesId")
        )
        track_id = normalize_category_value(
            feature_payload.get("track_id") or feature_payload.get("trackId")
        )
        car_id = normalize_category_value(
            feature_payload.get("car_id") or feature_payload.get("carId")
        )

        for feature_name in self.feature_names:
            value = feature_payload.get(feature_name)
            if value is None:
                # Handle one-hot encoded columns derived from base categorical IDs
                if feature_name.startswith("series_id_") and series_id is not None:
                    suffix = feature_name.split("series_id_", 1)[1]
                    value = 1.0 if suffix == series_id else 0.0
                elif feature_name.startswith("track_id_") and track_id is not None:
                    suffix = feature_name.split("track_id_", 1)[1]
                    value = 1.0 if suffix == track_id else 0.0
                elif feature_name.startswith("car_id_") and car_id is not None:
                    suffix = feature_name.split("car_id_", 1)[1]
                    value = 1.0 if suffix == car_id else 0.0
                else:
                    # Missing numeric feature defaults to 0 (consistent with training fallback)
                    value = 0.0
                    missing_count += 1

            vector.append(float(value))

        return np.array(vector, dtype=np.float32), missing_count

    def predict(self, feature_matrix: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Returns ensemble prediction and per-model predictions for confidence calculation.
        """
        if feature_matrix.ndim != 2:
            raise ValueError("Feature matrix must be 2D.")

        base_preds = []
        ensemble_pred = np.zeros(feature_matrix.shape[0], dtype=np.float32)
        for entry in self.models:
            model_pred = entry["model"].predict(feature_matrix).astype(np.float32)
            base_preds.append(model_pred)
            ensemble_pred += entry["weight"] * model_pred

        return ensemble_pred, np.vstack(base_preds)


_predictor_instances: Dict[str, EnsemblePredictor] = {}


def _default_model_dir() -> Path:
    env_dir = os.getenv("IRACING_ML_MODEL_DIR")
    if env_dir:
        return Path(env_dir).resolve()
    # Default: ../ghostx_front/ml_models relative to this file
    return (Path(__file__).parent.parent.parent / "ghostx_front" / "ml_models").resolve()


def _find_latest_config(model_dir: Path) -> Optional[Path]:
    configs = sorted(model_dir.glob("ensemble_config_*.json"))
    if configs:
        return configs[-1]
    return None


def _resolve_config_path(mode: str) -> Path:
    mode_upper = mode.upper()
    env_key = f"IRACING_ENSEMBLE_CONFIG_{mode_upper}"
    config_path_env = os.getenv(env_key)
    if config_path_env:
        return Path(config_path_env).resolve()

    model_dir = _default_model_dir() / mode
    config_path = _find_latest_config(model_dir)
    if config_path is None:
        raise FileNotFoundError(
            f"No ensemble_config_*.json found in {model_dir}. "
            f"Set {env_key} or run the training pipeline for mode '{mode}'."
        )
    return config_path


def get_predictor(mode: str = 'pre', force_reload: bool = False) -> EnsemblePredictor:
    mode = mode.lower()
    if mode not in ('pre', 'post'):
        raise ValueError("mode must be 'pre' or 'post'")

    global _predictor_instances
    if not force_reload and mode in _predictor_instances:
        return _predictor_instances[mode]

    config_path = _resolve_config_path(mode)
    predictor = EnsemblePredictor(config_path, mode=mode)
    _predictor_instances[mode] = predictor
    return predictor


def compute_confidence(per_model_preds: np.ndarray, ensemble_pred: np.ndarray) -> np.ndarray:
    """
    Estimate confidence based on agreement between models.
    Returns values in [0.4, 0.9].
    """
    if per_model_preds.shape[0] <= 1:
        return np.full_like(ensemble_pred, 0.5)

    std = np.std(per_model_preds, axis=0)
    denom = np.abs(ensemble_pred) + 1e-3
    agreement = 1 - (std / (denom))
    normalized = np.clip(0.4 + 0.3 * agreement, 0.4, 0.9)
    return normalized


def estimate_incident_probability(features: Dict[str, Optional[float]]) -> float:
    """
    Estimate incident probability based on historical data.
    Returns probability in [0.0, 1.0].
    """
    # 평균 사고율 기반으로 사고 발생 확률 추정
    avg_incidents_raw = features.get("avg_incidents_per_race")
    avg_incidents = float(avg_incidents_raw) if avg_incidents_raw is not None else 0.0
    
    dnf_rate_raw = features.get("dnf_rate")
    dnf_rate = float(dnf_rate_raw) if dnf_rate_raw is not None else 0.0
    
    high_risk_raw = features.get("high_incident_risk")
    high_risk = float(high_risk_raw) if high_risk_raw is not None else 0.0
    
    # 사고 발생 확률 = 평균 사고율이 0보다 크면 사고 발생 가능성 있음
    # 평균 사고율 1회 = 약 30% 확률, 2회 = 약 50%, 3회 이상 = 약 70%
    if avg_incidents <= 0:
        base_prob = 0.1  # 기본 10% 확률
    elif avg_incidents <= 1:
        base_prob = 0.3
    elif avg_incidents <= 2:
        base_prob = 0.5
    elif avg_incidents <= 3:
        base_prob = 0.7
    else:
        base_prob = 0.85
    
    # DNF율이 높으면 사고 확률 증가
    if dnf_rate > 0.3:
        base_prob = min(1.0, base_prob + 0.2)
    elif dnf_rate > 0.15:
        base_prob = min(1.0, base_prob + 0.1)
    
    # high_incident_risk 플래그가 있으면 추가 증가
    if high_risk > 0:
        base_prob = min(1.0, base_prob + 0.15)
    
    return min(1.0, max(0.0, base_prob))


def predict_with_incident_scenarios(
    base_prediction: float,
    incident_prob: float,
    incident_impact: float,
    total_participants: int = 20
) -> Dict[str, float]:
    """
    Predict finish position considering incident scenarios.
    
    Args:
        base_prediction: Base prediction (without incidents)
        incident_prob: Probability of having incidents (0.0-1.0)
        incident_impact: Average position drop when incidents occur (0.0-1.0, as finish_pct)
        total_participants: Total number of participants
    
    Returns:
        Dictionary with:
        - predicted_rank: Weighted average prediction
        - min_rank: Best case (no incidents)
        - max_rank: Worst case (severe incidents)
        - incident_risk_level: "low", "medium", "high"
    """
    # 시나리오 정의
    no_incident_prob = 1.0 - incident_prob
    minor_incident_prob = incident_prob * 0.6  # 1-2 incidents
    moderate_incident_prob = incident_prob * 0.3  # 3-5 incidents
    severe_incident_prob = incident_prob * 0.1  # 6+ incidents or DNF
    
    # 각 시나리오별 순위 하락 (완주율 단위)
    minor_drop = incident_impact * 0.3  # 경미한 사고: 30% 영향
    moderate_drop = incident_impact * 0.7  # 중간 사고: 70% 영향
    severe_drop = min(1.0, incident_impact * 1.5)  # 심각한 사고: 150% 영향 (최대 1.0)
    
    # 베이스 예측을 완주율로 변환 (예측값이 낮을수록 좋은 순위)
    base_finish_pct = base_prediction / total_participants if total_participants > 0 else 0.5
    
    # 각 시나리오별 예상 완주율
    scenario_no_incident = base_finish_pct
    scenario_minor = min(1.0, base_finish_pct + minor_drop)
    scenario_moderate = min(1.0, base_finish_pct + moderate_drop)
    scenario_severe = min(1.0, base_finish_pct + severe_drop)
    
    # 가중 평균 계산
    weighted_finish_pct = (
        scenario_no_incident * no_incident_prob +
        scenario_minor * minor_incident_prob +
        scenario_moderate * moderate_incident_prob +
        scenario_severe * severe_incident_prob
    )
    
    # 순위로 변환
    predicted_rank = max(1, int(weighted_finish_pct * total_participants))
    min_rank = max(1, int(scenario_no_incident * total_participants))
    max_rank = max(1, int(scenario_severe * total_participants))
    
    # 사고 위험도 레벨
    if incident_prob < 0.3:
        risk_level = "low"
    elif incident_prob < 0.6:
        risk_level = "medium"
    else:
        risk_level = "high"
    
    return {
        "predicted_rank": float(predicted_rank),
        "min_rank": float(min_rank),
        "max_rank": float(max_rank),
        "incident_risk_level": risk_level,
        "incident_probability": incident_prob,
    }

