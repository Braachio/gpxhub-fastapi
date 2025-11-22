from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.ml_predictor import (
    compute_confidence,
    estimate_incident_probability,
    get_predictor,
    predict_with_incident_scenarios,
)
import numpy as np

router = APIRouter()


class ParticipantPayload(BaseModel):
    cust_id: str = Field(..., alias="custId")
    features: Dict[str, Optional[float]]


class PredictRequest(BaseModel):
    participants: List[ParticipantPayload]


class ParticipantPrediction(BaseModel):
    cust_id: str = Field(..., alias="custId")
    predicted_finish: float
    rank: int
    confidence: float
    raw_score: float
    missing_features: int
    # 사고 시나리오 기반 예측
    incident_risk_level: Optional[str] = None  # "low", "medium", "high"
    incident_probability: Optional[float] = None  # 0.0-1.0
    predicted_rank_with_incidents: Optional[float] = None  # 사고 고려한 예측 순위
    min_rank: Optional[float] = None  # 최선의 경우 (사고 없음)
    max_rank: Optional[float] = None  # 최악의 경우 (심각한 사고)


class PredictResponse(BaseModel):
    mode: str
    model_version: Optional[str]
    feature_count: int
    predictions: List[ParticipantPrediction]


@router.post("/api/ml/predict-rank", response_model=PredictResponse)
async def predict_rank(payload: PredictRequest, mode: str = "pre"):
    mode = mode.lower()
    if mode not in {"pre", "post"}:
        raise HTTPException(status_code=400, detail="mode must be 'pre' or 'post'")

    if not payload.participants:
        raise HTTPException(status_code=400, detail="participants array cannot be empty")

    try:
        predictor = get_predictor(mode=mode)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"Failed to load model: {exc}") from exc

    feature_vectors = []
    missing_counts = []
    cust_ids: List[str] = []

    for participant in payload.participants:
        vector, missing = predictor.vectorize_features(participant.features or {})
        feature_vectors.append(vector)
        missing_counts.append(missing)
        cust_ids.append(participant.cust_id)

    matrix = np.vstack(feature_vectors)
    ensemble_pred, per_model_preds = predictor.predict(matrix)
    confidences = compute_confidence(per_model_preds, ensemble_pred)

    # Lower predicted finish indicates better rank
    order = np.argsort(ensemble_pred)
    ranks = np.empty_like(order)
    ranks[order] = np.arange(1, len(order) + 1)

    # 총 참가자 수 추정 (features에서 가져오거나 기본값 사용)
    total_participants = len(cust_ids)
    if payload.participants:
        first_participant_features = payload.participants[0].features or {}
        total_participants = int(first_participant_features.get("total_participants", len(cust_ids)))

    predictions = []
    for idx, cust_id in enumerate(cust_ids):
        participant_features = payload.participants[idx].features or {}
        
        # 사고 확률 추정
        incident_prob = estimate_incident_probability(participant_features)
        
        # 사고 영향도 가져오기
        incident_impact = abs(participant_features.get("incident_impact_on_position") or 0.0)
        if incident_impact == 0.0:
            # 기본값: 평균 사고율 기반 추정
            avg_incidents = participant_features.get("avg_incidents_per_race") or 0.0
            if avg_incidents is not None and avg_incidents > 0:
                incident_impact = min(0.3, float(avg_incidents) * 0.1)  # 사고 1회당 약 10% 순위 하락
        
        # 시나리오 기반 예측
        base_rank = float(ranks[idx])
        scenario_result = predict_with_incident_scenarios(
            base_prediction=base_rank,
            incident_prob=incident_prob,
            incident_impact=incident_impact,
            total_participants=total_participants
        )
        
        # 사고 위험도에 따른 신뢰도 조정
        base_confidence = float(confidences[idx])
        incident_risk_factor = incident_prob * 0.3  # 사고 확률이 높을수록 신뢰도 감소
        adjusted_confidence = base_confidence * (1 - incident_risk_factor)
        
        predictions.append(
            ParticipantPrediction(
                custId=cust_id,
                predicted_finish=float(ensemble_pred[idx]),
                rank=int(ranks[idx]),
                confidence=float(adjusted_confidence),
                raw_score=float(ensemble_pred[idx]),
                missing_features=int(missing_counts[idx]),
                incident_risk_level=scenario_result["incident_risk_level"],
                incident_probability=round(incident_prob, 3),
                predicted_rank_with_incidents=scenario_result["predicted_rank"],
                min_rank=scenario_result["min_rank"],
                max_rank=scenario_result["max_rank"],
            )
        )

    return PredictResponse(
        mode=mode,
        model_version=predictor.model_version,
        feature_count=len(predictor.feature_names),
        predictions=predictions,
    )

