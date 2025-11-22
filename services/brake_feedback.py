from supabase import create_client
import os

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def generate_braking_feedback(lap_id: str, track: str) -> list[str]:
    """
    본인보다 sector time이 빠른 랩들의 brake_start_dist 평균을 기준으로 피드백 생성
    """
    feedbacks = []

    # 1️⃣ 현재 랩의 브레이크 분석 데이터와 섹터 타임 데이터 가져오기
    current_brakes = supabase.table("brake_analysis").select("*").eq("lap_id", lap_id).execute().data
    current_sectors = supabase.table("sector_results").select("*").eq("lap_id", lap_id).execute().data
    if not current_brakes or not current_sectors:
        return ["❌ 현재 랩에 대한 분석 데이터가 부족합니다."]

    for brake in current_brakes:
        corner_index = brake["corner_index"]
        my_dist = brake.get("brake_start_dist")
        if my_dist is None:
            feedbacks.append(f"코너 {corner_index + 1}: 현재 브레이크 데이터가 없습니다.")
            continue

        my_sector = next((s for s in current_sectors if s["sector_index"] == corner_index), None)
        if not my_sector:
            feedbacks.append(f"코너 {corner_index + 1}: 현재 섹터 타임을 찾을 수 없습니다.")
            continue
        my_time = my_sector["sector_time"]

        # 2️⃣ 더 빠른 섹터 타임을 가진 랩 ID 리스트 가져오기
        faster_laps_resp = supabase.table("sector_results") \
            .select("lap_id") \
            .match({"track": track, "sector_index": corner_index}) \
            .lt("sector_time", my_time) \
            .neq("lap_id", lap_id) \
            .execute()

        faster_lap_ids = [row["lap_id"] for row in (faster_laps_resp.data or [])]

        if not faster_lap_ids:
            feedbacks.append(f"코너 {corner_index + 1}: 비교할 수 있는 더 빠른 랩이 없습니다.")
            continue

        # 3️⃣ brake_analysis에서 빠른 랩들의 brake_start_dist 가져오기
        brake_resp = supabase.table("brake_analysis") \
            .select("brake_start_dist") \
            .in_("lap_id", faster_lap_ids) \
            .eq("track", track) \
            .eq("corner_index", corner_index) \
            .execute()

        values = [r["brake_start_dist"] for r in (brake_resp.data or []) if r["brake_start_dist"] is not None]
        if not values or len(values) < 3:
            feedbacks.append(f"코너 {corner_index + 1}: 비교할 수 있는 유효한 데이터가 부족합니다.")
            continue

        # 4️⃣ 평균/표준편차 계산 및 피드백 생성
        avg = sum(values) / len(values)
        std = (sum((x - avg) ** 2 for x in values) / len(values)) ** 0.5
        diff = my_dist - avg

        print(f"🔍 코너 {corner_index}: 내 = {my_dist:.2f}, 빠른 평균 = {avg:.2f}, std = {std:.2f}")

        if diff < -std:
            feedbacks.append(f"코너 {corner_index + 1}: 브레이킹이 빠른 랩들보다 {abs(diff):.1f}m 빠릅니다. 더 늦게 브레이크를 밟아보세요.")
        elif diff > std:
            feedbacks.append(f"코너 {corner_index + 1}: 브레이킹이 빠른 랩들보다 {abs(diff):.1f}m 늦습니다. 조금 더 일찍 브레이크를 시작해보세요.")
        else:
            feedbacks.append(f"코너 {corner_index + 1}: 브레이킹 타이밍이 빠른 랩들과 유사합니다.")

    return feedbacks
