from typing import Dict, Literal

AnalysisMode = Literal["throttle", "braking"]
DriverLevel = Literal["beginner", "intermediate", "advanced"]

def build_feedback_prompt(
    segment: Dict,
    segment_index: int,
    mode: AnalysisMode = "throttle",
    driver_level: DriverLevel = "beginner"
) -> str:
    """
    분석 모드(throttle or braking)에 따라 초보자용 피드백 프롬프트 생성
    """
    if driver_level != "beginner":
        raise ValueError("현재는 beginner 레벨만 지원합니다.")

    if mode == "throttle":
        return _build_throttle_prompt(segment, segment_index)
    elif mode == "braking":
        return _build_braking_prompt(segment, segment_index)
    else:
        raise ValueError(f"지원하지 않는 분석 모드입니다: {mode}")


def _build_throttle_prompt(segment: Dict, index: int) -> str:
    base_data = f"""
- 최대 슬립 비율: {segment.get('max_slip_ratio', 0):.2f}
- 평균 스로틀 기울기: {segment.get('avg_throttle_gradient', 0):.3f}
- 조향 안정성 (조향각 변화량 평균): {segment.get('steer_variability', 0):.2f}
- 좌우 휠 속도 차이: {segment.get('wheel_slip_lr', 0):.2f}
- 전후 휠 속도 차이: {segment.get('wheel_slip_fb', 0):.2f}
"""

    return f"""
당신은 초보 드라이버를 지도하는 친절한 레이싱 코치입니다.

다음은 코너 {index + 1} 탈출 분석 결과입니다:
{base_data}

초보자도 이해할 수 있게 **쉬운 말로**,  
운전 습관을 **칭찬 + 조언** 형태로 2~3문장 작성해주세요.
"""


def _build_braking_prompt(segment: Dict, index: int) -> str:
    base_data = f"""
- 브레이크 시작 시간: {segment.get('start_time', 0):.2f}초
- 종료 시간: {segment.get('end_time', 0):.2f}초
- 브레이크 유지 시간: {segment.get('duration', 0):.2f}초
- 평균 감속률: {segment.get('avg_deceleration', 0):.2f}
- 조향각 변화량: {segment.get('steer_variability', 0):.2f}
"""

    return f"""
당신은 초보 드라이버를 지도하는 친절한 레이싱 코치입니다.

다음은 코너 진입 시 트레일 브레이킹 분석 결과입니다 (구간 {index + 1}):
{base_data}

초보자도 이해할 수 있게 **쉬운 말로**,  
브레이크와 조향의 연계에 대해 **칭찬 + 개선점**을 중심으로 2~3문장 작성해주세요.
"""
