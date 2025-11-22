from typing import Any, Dict, List, Optional, Tuple
import logging

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.ml_predictor import (
    compute_confidence,
    estimate_incident_probability,
    get_predictor,
    predict_with_incident_scenarios,
)

router = APIRouter()
logger = logging.getLogger("predict")


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
    incident_risk_level: Optional[str] = None
    incident_probability: Optional[float] = None
    predicted_rank_with_incidents: Optional[float] = None
    min_rank: Optional[float] = None
    max_rank: Optional[float] = None
    analyzed_factors: List[str] = Field(default_factory=list)
    actionable_insights: List[str] = Field(default_factory=list)
    rival_front: Optional[Dict[str, Any]] = None
    rival_rear: Optional[Dict[str, Any]] = None


class PredictResponse(BaseModel):
    mode: str
    model_version: Optional[str]
    feature_count: int
    predictions: List[ParticipantPrediction]


IMPORTANCE_THRESHOLD = 0.01
NEIGHBOR_RANGE = 2


def _safe_float(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_starting_position_negative(value: float) -> str:
    return f"스타트 그리드 P{int(value) + 1}에서 출발해 초반 추월 전략이 필요합니다."


def _format_starting_position_positive(value: float) -> str:
    return f"앞선 스타트 위치(P{int(value) + 1})를 활용해 레이스 초반 주도권을 잡아보세요."


def _format_ir_diff_negative(value: float) -> str:
    return f"로비 평균보다 iRating이 {abs(int(value))} 낮아 어려운 승부가 예상됩니다."


def _format_ir_diff_positive(value: float) -> str:
    return f"iRating 우위({int(value)} 포인트)가 있어 상위권 경쟁이 가능합니다."


def _format_incidents_negative(value: float) -> str:
    return f"평균 INC {value:.1f}로 사고 위험이 높습니다. 안정적인 주행이 필요합니다."


def _format_incidents_positive(value: float) -> str:
    return f"평균 INC {value:.1f}로 깔끔한 주행이 강점입니다."


def _format_safety_negative(value: float) -> str:
    return f"Safety Rating {value:.2f}로 실수 최소화가 필요합니다."


def _format_safety_positive(value: float) -> str:
    return f"Safety Rating {value:.2f}로 안정적인 주행 능력이 돋보입니다."


def _format_winrate_positive(value: float) -> str:
    return f"우승률 {value:.1f}%의 페이스가 강점입니다."


def _format_dnf_negative(value: float) -> str:
    return f"DNF 비율 {value:.0%}로 완주 전략이 필요합니다."


def _format_consistency_negative(value: float) -> str:
    return f"평균 순위 {value:.1f}로 최근 컨디션이 아쉽습니다."


def _format_consistency_positive(value: float) -> str:
    return f"평균 순위 {value:.1f}로 최근 흐름이 좋습니다."


FEATURE_RULES = {
    "starting_position": {
        "direction": "lower",
        "bad_threshold": 12,
        "good_threshold": 5,
        "negative": _format_starting_position_negative,
        "positive": _format_starting_position_positive,
    },
    "ir_diff_from_avg": {
        "direction": "diff",
        "bad_threshold": -150,
        "good_threshold": 150,
        "negative": _format_ir_diff_negative,
        "positive": _format_ir_diff_positive,
    },
    "avg_incidents_per_race": {
        "direction": "lower",
        "bad_threshold": 3.0,
        "good_threshold": 1.5,
        "negative": _format_incidents_negative,
        "positive": _format_incidents_positive,
    },
    "safety_rating": {
        "direction": "higher",
        "bad_threshold": 2.5,
        "good_threshold": 3.5,
        "negative": _format_safety_negative,
        "positive": _format_safety_positive,
    },
    "dnf_rate": {
        "direction": "lower",
        "bad_threshold": 0.3,
        "good_threshold": 0.1,
        "negative": _format_dnf_negative,
        "positive": lambda value: f"DNF 비율 {value:.0%}로 완주 안정성이 강점입니다.",
    },
    "win_rate": {
        "direction": "higher",
        "bad_threshold": 5.0,
        "good_threshold": 15.0,
        "negative": lambda value: f"우승률 {value:.1f}%로 상위권 경험이 부족한 편입니다.",
        "positive": _format_winrate_positive,
    },
    "top5_rate": {
        "direction": "higher",
        "bad_threshold": 10.0,
        "good_threshold": 30.0,
        "negative": lambda value: f"TOP5 비율 {value:.1f}%로 상위권 경험이 적습니다.",
        "positive": lambda value: f"TOP5 꾸준함({value:.1f}%)이 강점입니다.",
    },
    "recent_avg_finish_position": {
        "direction": "lower",
        "bad_threshold": 12.0,
        "good_threshold": 6.0,
        "negative": _format_consistency_negative,
        "positive": _format_consistency_positive,
    },
}


def _compute_direction_scores(direction: str, value: Optional[float], bad: Optional[float], good: Optional[float]):
    negative_score = 0.0
    positive_score = 0.0

    if value is None:
        return negative_score, positive_score

    if direction == "lower":
        if bad is not None and value > bad:
            negative_score = min(1.5, (value - bad) / max(bad, 1.0))
        if good is not None and value <= good:
            positive_score = min(1.5, (good - value) / max(good, 1.0))
    elif direction == "higher":
        if bad is not None and value < bad:
            negative_score = min(1.5, (bad - value) / max(abs(bad), 1.0))
        if good is not None and value >= good:
            positive_score = min(1.5, (value - good) / max(good, 1.0))
    elif direction == "diff":
        if bad is not None and value < bad:
            negative_score = min(1.5, abs(value - bad) / max(abs(bad), 1.0))
        if value < 0 and bad is not None and value < 0:
            negative_score = min(1.5, abs(value) / max(abs(bad), 1.0))
        if good is not None and value > good:
            positive_score = min(1.5, abs(value - good) / max(abs(good), 1.0))
        if value > 0 and good is not None:
            positive_score = min(1.5, value / max(abs(good), 1.0))
    return negative_score, positive_score


def analyze_feature_factors(
    feature_importances: Optional[Dict[str, float]],
    features: Dict[str, Optional[float]],
) -> Tuple[List[str], List[str]]:
    if not feature_importances:
        return [], []

    negative_scores: List[Tuple[float, str]] = []
    positive_scores: List[Tuple[float, str]] = []

    for feature_name, importance in sorted(feature_importances.items(), key=lambda item: item[1], reverse=True):
        if importance < IMPORTANCE_THRESHOLD:
            continue
        rule = FEATURE_RULES.get(feature_name)
        if not rule:
            continue

        value = _safe_float(features.get(feature_name))
        negative, positive = _compute_direction_scores(
            direction=rule.get("direction", "higher"),
            value=value,
            bad=rule.get("bad_threshold"),
            good=rule.get("good_threshold"),
        )

        if negative > 0 and callable(rule.get("negative")) and value is not None:
            negative_scores.append((importance * negative, rule["negative"](value)))
        if positive > 0 and callable(rule.get("positive")) and value is not None:
            positive_scores.append((importance * positive, rule["positive"](value)))

    negative_scores.sort(key=lambda item: item[0], reverse=True)
    positive_scores.sort(key=lambda item: item[0], reverse=True)

    analyzed = [msg for _, msg in negative_scores[:3]]
    actionable = [msg for _, msg in positive_scores[:3]]
    return analyzed, actionable


def _safe_grid_position(features: Dict[str, Optional[float]]) -> Optional[float]:
    value = features.get("starting_position")
    normalized = _safe_float(value)
    if normalized is None:
        return None
    if normalized > 100:
        return normalized - 1
    return normalized


def _build_neighbor_map(participants: List[ParticipantPayload]) -> Dict[int, Dict[str, List[int]]]:
    start_positions: List[Tuple[int, float]] = []
    fallback_counter = 0
    for idx, participant in enumerate(participants):
        position = _safe_grid_position(participant.features or {})
        if position is None:
            position = 10_000 + fallback_counter
            fallback_counter += 1
        start_positions.append((idx, position))

    start_positions.sort(key=lambda item: item[1])
    neighbor_map: Dict[int, Dict[str, List[int]]] = {}

    for order_idx, (participant_idx, _) in enumerate(start_positions):
        ahead: List[int] = []
        behind: List[int] = []

        for offset in range(1, NEIGHBOR_RANGE + 1):
            ahead_idx = order_idx - offset
            if ahead_idx >= 0:
                ahead.append(start_positions[ahead_idx][0])

            behind_idx = order_idx + offset
            if behind_idx < len(start_positions):
                behind.append(start_positions[behind_idx][0])

        neighbor_map[participant_idx] = {
            "ahead": ahead,
            "behind": behind,
            "neighbors": ahead + behind,
        }

    return neighbor_map


def _format_neighbor_position(features: Dict[str, Optional[float]]) -> Optional[int]:
    start_pos = _safe_grid_position(features)
    if start_pos is None:
        return None
    return int(round(start_pos)) + 1


def _generate_danger_insight(
    neighbors: List[int],
    idx: int,
    participants: List[ParticipantPayload],
) -> Optional[str]:
    if not neighbors:
        return None

    incidents: List[float] = []
    dnfs: List[float] = []
    for neighbor_idx in neighbors:
        feats = participants[neighbor_idx].features or {}
        inc = _safe_float(feats.get("avg_incidents_per_race"))
        dnf = _safe_float(feats.get("dnf_rate"))
        if inc is not None:
            incidents.append(inc)
        if dnf is not None:
            dnfs.append(dnf)

    if not incidents and not dnfs:
        return None

    avg_inc = sum(incidents) / len(incidents) if incidents else None
    avg_dnf = sum(dnfs) / len(dnfs) if dnfs else None

    if (avg_inc is not None and avg_inc >= 1.5) or (avg_dnf is not None and avg_dnf >= 0.15):
        inc_text = f"{avg_inc:.1f}" if avg_inc is not None else "N/A"
        dnf_text = f"{(avg_dnf or 0) * 100:.0f}%" if avg_dnf is not None else "N/A"
        return (
            f"⚠️ 주변 그리드 평균 사고율 {inc_text}회, DNF {dnf_text} 수준입니다. "
            "스타트 구간에서 라인을 넓게 쓰고 접촉을 피하세요."
        )
    return None


def _generate_prey_insight(
    current_idx: int,
    ahead_indices: List[int],
    participants: List[ParticipantPayload],
    total_participants: int,
) -> Optional[str]:
    if not ahead_indices:
        return None

    my_features = participants[current_idx].features or {}
    my_ir = _safe_float(my_features.get("i_rating"))
    best_candidate = None
    best_score = -1.0

    for idx in ahead_indices:
        feats = participants[idx].features or {}
        opp_recent = _safe_float(feats.get("recent_avg_finish_position"))
        opp_ir = _safe_float(feats.get("i_rating"))
        opp_start_pos = _safe_grid_position(feats)
        opp_inc = _safe_float(feats.get("avg_incidents_per_race"))

        finish_score = 0.0
        if opp_recent is not None and total_participants > 0:
            finish_pct = opp_recent / total_participants
            if finish_pct >= 0.6:
                finish_score += finish_pct

        ir_gap_score = 0.0
        if my_ir is not None and opp_ir is not None:
            diff = my_ir - opp_ir
            if diff >= 120:
                ir_gap_score += diff / 500

        incident_score = 0.0
        if opp_inc is not None and opp_inc >= 2.5:
            incident_score += (opp_inc - 2.0) / 3

        total_score = finish_score + ir_gap_score + incident_score
        if total_score > best_score and opp_start_pos is not None:
            best_score = total_score
            best_candidate = (idx, opp_start_pos, opp_recent, opp_ir)

    if best_candidate is None or best_score < 0.2:
        return None

    idx, start_pos, recent_pos, opp_ir = best_candidate
    grid_text = int(round(start_pos)) + 1
    detail_parts = []
    if recent_pos is not None and total_participants > 0:
        finish_pct = recent_pos / total_participants * 100
        detail_parts.append(f"최근 평균 완주 순위 {finish_pct:.0f}% 구간")
    if opp_ir is not None and my_ir is not None:
        ir_gap = my_ir - opp_ir
        if ir_gap >= 120:
            detail_parts.append(f"iRating 열세 {int(ir_gap)}")
    detail = " / ".join(detail_parts)
    return (
        f"🎯 P{grid_text} 드라이버는 {detail} 지표가 약합니다. "
        "초반부터 압박해 실수를 유도하십시오."
    )


def _generate_pace_insight(
    current_idx: int,
    neighbor_indices: List[int],
    participants: List[ParticipantPayload],
) -> Optional[str]:
    my_features = participants[current_idx].features or {}
    my_ir = _safe_float(my_features.get("i_rating"))
    my_qual = _safe_float(
        my_features.get("qualifying_best_lap_time")
        or my_features.get("fastest_qualifying_lap_time")
        or my_features.get("practice_best_lap_time")
    )

    if my_qual is None:
        return None

    neighbor_laps = []
    for idx in neighbor_indices:
        feats = participants[idx].features or {}
        lap = _safe_float(
            feats.get("qualifying_best_lap_time")
            or feats.get("fastest_qualifying_lap_time")
            or feats.get("practice_best_lap_time")
        )
        if lap is not None:
            neighbor_laps.append(lap)

    if not neighbor_laps:
        return None

    avg_neighbor_lap = sum(neighbor_laps) / len(neighbor_laps)
    advantage = avg_neighbor_lap - my_qual
    if advantage >= 0.25:
        pace_tone = (
            "🚀 단기 페이스가 상위 그룹 수준입니다. "
            "스타트 이후 깨끗한 공기를 확보해 리듬을 만들면 우승권 싸움이 가능합니다."
        )
        if my_ir is not None:
            pace_tone = (
                f"{pace_tone} (현재 랩타임 우위 {advantage:.2f}s / iRating {int(my_ir)} 기준)"
            )
        return pace_tone
    return None


def _generate_sprint_playbook(
    participants: List[ParticipantPayload],
    current_idx: int,
    ahead_indices: List[int],
    behind_indices: List[int],
    total_participants: int,
) -> Tuple[List[str], List[str]]:
    analyzed: List[str] = []
    actionable: List[str] = []

    main_features = participants[current_idx].features or {}
    main_start = _safe_grid_position(main_features)
    main_ir = _safe_float(main_features.get("i_rating"))
    my_inc = _safe_float(main_features.get("avg_incidents_per_race"))
    my_qual = _safe_float(
        main_features.get("qualifying_best_lap_time")
        or main_features.get("fastest_qualifying_lap_time")
        or main_features.get("practice_best_lap_time")
    )
    total = total_participants or len(participants)

    if main_start is not None and total > 0:
        start_pct = (main_start + 1) / total
        if start_pct <= 0.15:
            analyzed.append(
                "🚦 프런트 스프린트: 초반 2랩 안에 격차를 벌리면 끝까지 리드가 가능합니다."
            )
            actionable.append(
                "Lap1 T1에서 인사이드 라인을 선점하고 Lap2까지 깨끗한 공기를 확보하세요."
            )
        elif start_pct <= 0.65:
            analyzed.append(
                "📊 중위권 혼전: 스프린트는 피트 전략이 없으므로 첫 3랩 포지션 관리가 핵심입니다."
            )
            actionable.append(
                "초반 혼전 구간에서는 사고 가능성이 높은 외곽을 피하고 Lap2~3 슬립스트림으로 압박하세요."
            )
        else:
            analyzed.append(
                "🛡️ 후미 스타트: 앞쪽 사고를 피하고 빈 공간을 활용해 여러 대를 한 번에 추월해야 합니다."
            )
            actionable.append(
                "Lap1 두 코너 동안 시야를 넓히고, 브레이크 포인트를 지키면서 안전하게 포지션을 올리세요."
            )

    if my_inc is not None and my_inc >= 3.0:
        actionable.append(
            "⚠️ 최근 평균 INC가 높습니다. Lap1 브레이킹을 평소보다 한 차량 길이 늦게 가져가 사고를 줄이세요."
        )

    if ahead_indices and my_qual is not None:
        front_feats = participants[ahead_indices[0]].features or {}
        front_qual = _safe_float(
            front_feats.get("qualifying_best_lap_time")
            or front_feats.get("fastest_qualifying_lap_time")
            or front_feats.get("practice_best_lap_time")
        )
        if front_qual is not None:
            lap_diff = front_qual - my_qual
            if lap_diff >= 0.15:
                actionable.append(
                    "🚀 앞차보다 퀄리파잉 타임이 0.15초 이상 빠릅니다. Lap2~4에 클린 에어를 확보해 추월을 시도하세요."
                )
            elif lap_diff <= -0.1:
                analyzed.append(
                    "🌀 앞차가 단일 랩 페이스에서 우위입니다. 초반에는 슬립스트림으로 에너지를 아끼는 편이 좋습니다."
                )

    if behind_indices and main_ir is not None:
        rear_feats = participants[behind_indices[0]].features or {}
        rear_ir = _safe_float(rear_feats.get("i_rating"))
        rear_inc = _safe_float(rear_feats.get("avg_incidents_per_race"))
        if rear_ir is not None and rear_ir - main_ir >= 150:
            actionable.append(
                "🛡️ 뒤차 iRating이 높습니다. Lap1 T1에서 한 번만 인사이드 라인을 봉쇄하고, 이후에는 깨끗한 레이스 라인을 유지하세요."
            )
        elif rear_inc is not None and rear_inc >= 3.5:
            actionable.append(
                "⚠️ 뒤차 사고율이 높습니다. 억지 방어보다는 라인을 살짝 열어 사고를 피한 뒤 다시 추월을 노리세요."
            )

    return analyzed, actionable


def generate_field_analysis_insights(
    participants: List[ParticipantPayload],
    current_idx: int,
    total_participants: int,
    neighbor_map: Dict[int, Dict[str, List[int]]],
) -> Tuple[List[str], List[str], Dict[str, Dict[str, Any]]]:
    neighbors_info = neighbor_map.get(current_idx, {"ahead": [], "behind": [], "neighbors": []})
    analyzed: List[str] = []
    actionable: List[str] = []
    rival_cards: Dict[str, Dict[str, Any]] = {}

    main_features = participants[current_idx].features or {}
    main_ir = _safe_float(main_features.get("i_rating"))
    main_start = _safe_grid_position(main_features)

    ahead_indices = neighbors_info.get("ahead", [])
    behind_indices = neighbors_info.get("behind", [])
    target_idx = ahead_indices[0] if ahead_indices else None
    threat_idx = behind_indices[0] if behind_indices else None

    danger = _generate_danger_insight(
        neighbors_info.get("neighbors", []),
        current_idx,
        participants,
    )
    if danger:
        analyzed.append(danger)

    prey = _generate_prey_insight(
        current_idx,
        ahead_indices,
        participants,
        total_participants,
    )
    if prey:
        actionable.append(prey)

    pace = _generate_pace_insight(
        current_idx,
        neighbors_info.get("neighbors", []),
        participants,
    )
    if pace:
        actionable.append(pace)

    sprint_analyzed, sprint_actionable = _generate_sprint_playbook(
        participants,
        current_idx,
        ahead_indices,
        behind_indices,
        total_participants,
    )
    analyzed.extend(sprint_analyzed)
    actionable.extend(sprint_actionable)

    # Tactical rivalry analysis
    def grid_text(idx: int) -> str:
        feats = participants[idx].features or {}
        pos = _safe_grid_position(feats)
        if pos is None:
            return "앞차" if idx == target_idx else "뒷차"
        return f"P{int(round(pos)) + 1}"

    def append_analysis(msg: Optional[str], target_list: List[str]) -> None:
        if msg:
            target_list.append(msg)

    def build_rival_card(label: str, opp_idx: int, is_front: bool) -> Optional[Dict[str, Any]]:
        feats = participants[opp_idx].features or {}
        pos = _safe_grid_position(feats)
        ir = _safe_float(feats.get("i_rating"))
        incidents = _safe_float(feats.get("avg_incidents_per_race"))
        dnf = _safe_float(feats.get("dnf_rate"))
        recent = _safe_float(feats.get("recent_avg_finish_position"))

        card: Dict[str, Any] = {"label": label, "position": grid_text(opp_idx)}

        if main_ir is not None and ir is not None:
            ir_delta = ir - main_ir
            if abs(ir_delta) >= 40:
                if is_front:
                    tendency = "강한 페이스" if ir_delta > 0 else "추월권"
                else:
                    tendency = "강한 상대" if ir_delta > 0 else "추월권"
                card["irGap"] = f"{ir_delta:+.0f} iR ({tendency})"

        if incidents is not None:
            card["incidents"] = f"사고율 {incidents:.1f}"
        if dnf is not None:
            card["dnf"] = f"DNF {dnf * 100:.0f}%"
        if recent is not None:
            card["recent"] = f"최근 완주 P{int(round(recent))}"

        advice: Optional[str] = None
        if is_front:
            if incidents is not None and incidents >= 3.5:
                advice = "Lap1 접촉 위험. 첫 코너에서 무리하지 말고, Lap2부터 압박하세요."
            elif dnf is not None and dnf >= 0.2:
                advice = "완주 불안한 상대입니다. 초반 두 코너에서 라인을 넓게 쓰게 만들어 실수를 유도하세요."
            elif main_ir is not None and ir is not None and main_ir - ir >= 150:
                advice = "iRating 우위입니다. 스타트 후 2랩 이내에 페이스로 눌러주세요."
            else:
                advice = "초반 3랩 동안 슬립스트림을 유지하며 기회를 노리세요."
        else:
            if incidents is not None and incidents >= 3.5:
                advice = "뒤차 사고율이 높습니다. Lap1 초반에는 라인을 잠깐 열어주고 리듬을 되찾으세요."
            elif main_ir is not None and ir is not None and ir - main_ir >= 150:
                advice = "강한 상대가 뒤에 있습니다. 첫 두 코너에서 인사이드 라인을 지키고 이후 안정적으로 주행하세요."
            else:
                advice = "뒤차를 이용해 토우를 받되, 브레이크 포인트를 흔들지 마세요."

        card["advice"] = advice
        return card if len(card) > 2 else None

    if target_idx is not None:
        card = build_rival_card("전방", target_idx, True)
        if card:
            rival_cards["front"] = card
        target_feats = participants[target_idx].features or {}
        target_inc = _safe_float(target_feats.get("avg_incidents_per_race"))
        target_dnf = _safe_float(target_feats.get("dnf_rate"))
        if target_inc is not None and target_inc > 5.0:
            analyzed.append(
                f"⚠️ 전방 주의: {grid_text(target_idx)} 평균 사고율 {target_inc:.1f}회입니다."
            )
        if target_dnf is not None and target_dnf > 0.15:
            analyzed.append(
                f"⚠️ 전방 주의: {grid_text(target_idx)} DNF 비율이 {target_dnf * 100:.0f}%입니다."
            )
        target_ir = _safe_float(target_feats.get("i_rating"))
        if main_ir is not None and target_ir is not None and main_ir > target_ir + 150:
            actionable.append(
                f"🚀 추월 기회: {grid_text(target_idx)} 대비 iRating {int(main_ir - target_ir)} 우위입니다. "
                "초반 두 랩 동안 압박하여 실수를 유도하세요."
            )
        target_recent = _safe_float(target_feats.get("recent_avg_finish_position"))
        target_avg = _safe_float(target_feats.get("avg_finish_position"))
        if (
            target_recent is not None
            and target_avg is not None
            and target_recent > target_avg + 2
        ):
            actionable.append(
                f"🎯 타겟 포착: {grid_text(target_idx)}는 최근 완주 평균이 평소보다 {target_recent - target_avg:.1f}위 악화됐습니다. "
                "멘탈이 흔들릴 수 있으니 초반부터 압박하세요."
            )

    if threat_idx is not None:
        card = build_rival_card("후방", threat_idx, False)
        if card:
            rival_cards["rear"] = card
        threat_feats = participants[threat_idx].features or {}
        threat_inc = _safe_float(threat_feats.get("avg_incidents_per_race"))
        if threat_inc is not None and threat_inc > 5.0:
            analyzed.append(
                f"🛡️ 후방 주의: {grid_text(threat_idx)} 평균 사고율 {threat_inc:.1f}회로 공격적인 타입입니다."
            )
        threat_ir = _safe_float(threat_feats.get("i_rating"))
        if main_ir is not None and threat_ir is not None and threat_ir > main_ir + 350:
            analyzed.append(
                f"⚠️ 고수 감지: 뒤차 {grid_text(threat_idx)}는 iRating이 {int(threat_ir - main_ir)} 높습니다. "
                "불필요한 블로킹보다 클린한 라인을 유지해 손실을 줄이세요."
            )
    # Grid-based context insights
    if main_start is not None and total_participants > 0:
        start_pct = (main_start + 1) / total_participants
        if start_pct <= 0.15:
            analyzed.append("✅ 프런트 로우에서 출발합니다. 스타트 크리트럴 구간에서 최대치의 런을 노리세요.")
        elif start_pct >= 0.8:
            analyzed.append("⚠️ 후방 스타트입니다. 첫 코너 충돌을 피하기 위해 시야를 넓게 유지하세요.")

    if "front" not in rival_cards and target_idx is not None:
        rival_cards["front"] = {
            "label": "전방",
            "position": grid_text(target_idx),
            "advice": "초반 압박으로 추월 기회를 노리세요.",
        }
    if "rear" not in rival_cards and threat_idx is not None:
        rival_cards["rear"] = {
            "label": "후방",
            "position": grid_text(threat_idx),
            "advice": "후방 견제를 대비하세요.",
        }

    if not analyzed:
        analyzed.append("⚠️ 초반 혼전에 대비하세요. 주변 iRating 분산이 큰 편입니다.")
    if not actionable:
        actionable.append("🎯 레이스 초반 2랩 동안 타이어를 예열하고 안정적으로 페이스를 맞추세요.")

    return analyzed, actionable, rival_cards


@router.post("/predict-rank", response_model=PredictResponse)
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
    except Exception as exc:
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

    order = np.argsort(ensemble_pred)
    ranks = np.empty_like(order)
    ranks[order] = np.arange(1, len(order) + 1)

    total_participants = len(cust_ids)
    if payload.participants:
        first_features = payload.participants[0].features or {}
        total_participants = int(first_features.get("total_participants", len(cust_ids)))

    neighbor_map = _build_neighbor_map(payload.participants)
    predictions = []
    importance_map = predictor.feature_importances

    for idx, cust_id in enumerate(cust_ids):
        participant_features = payload.participants[idx].features or {}

        incident_prob = estimate_incident_probability(participant_features)
        incident_impact = abs(participant_features.get("incident_impact_on_position") or 0.0)
        if incident_impact == 0.0:
            avg_incidents = participant_features.get("avg_incidents_per_race") or 0.0
            if avg_incidents is not None and avg_incidents > 0:
                incident_impact = min(0.3, float(avg_incidents) * 0.1)

        base_rank = float(ranks[idx])
        scenario_result = predict_with_incident_scenarios(
            base_prediction=base_rank,
            incident_prob=incident_prob,
            incident_impact=incident_impact,
            total_participants=total_participants,
        )

        base_confidence = float(confidences[idx])
        incident_risk_factor = incident_prob * 0.3
        adjusted_confidence = base_confidence * (1 - incident_risk_factor)

        analyzed_factors, actionable_insights = analyze_feature_factors(importance_map, participant_features)
        field_analyzed, field_actionable, rival_cards = generate_field_analysis_insights(
            payload.participants,
            idx,
            total_participants,
            neighbor_map,
        )
        logger.info(
            "Field insights for %s (rank %s): analyzed=%s actionable=%s rivals=%s",
            cust_id,
            ranks[idx],
            field_analyzed,
            field_actionable,
            rival_cards,
        )
        analyzed_factors.extend(field_analyzed)
        actionable_insights.extend(field_actionable)

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
                analyzed_factors=analyzed_factors,
                actionable_insights=actionable_insights,
                rival_front=rival_cards.get("front"),
                rival_rear=rival_cards.get("rear"),
            )
        )

    return PredictResponse(
        mode=mode,
        model_version=predictor.model_version,
        feature_count=len(predictor.feature_names),
        predictions=predictions,
    )

