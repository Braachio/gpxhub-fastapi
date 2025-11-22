from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from utils.supabase_client import supabase
from utils.sanitize import sanitize_for_json
from services.lap_data import fetch_lap_meta_and_data
from services.fixed_sector import get_sector_summary_by_lap_id
from services.braking_dynamics import analyze_braking_dynamics
from services.track_corners import get_corner_segments_for_track

router = APIRouter()

@router.get("/dashboard/overview/{user_id}")
async def get_dashboard_overview(
    user_id: str,
    track: Optional[str] = Query(None, description="특정 트랙 필터링"),
    days: int = Query(30, description="조회 기간 (일)")
):
    """
    사용자 대시보드 개요 데이터 제공
    - 최근 랩 요약
    - 성능 트렌드
    - 핵심 지표
    """
    try:
        # 1️⃣ 최근 랩 메타데이터 조회
        date_filter = datetime.now() - timedelta(days=days)
        
        query = supabase.table("lap_meta").select("*").eq("user_id", user_id)
        if track:
            query = query.eq("track", track.lower())
        
        recent_laps = query.gte("created_at", date_filter.isoformat()).order("created_at", desc=True).limit(20).execute()
        
        if not recent_laps.data:
            return {
                "user_id": user_id,
                "track": track,
                "period_days": days,
                "total_laps": 0,
                "summary": {
                    "best_lap_time": None,
                    "average_lap_time": None,
                    "improvement_trend": None,
                    "total_distance": 0
                },
                "recent_laps": [],
                "performance_metrics": {},
                "track_leaderboard": []
            }

        # 2️⃣ 기본 통계 계산
        lap_times = [lap["lap_time"] for lap in recent_laps.data if lap["lap_time"]]
        best_lap_time = min(lap_times) if lap_times else None
        avg_lap_time = sum(lap_times) / len(lap_times) if lap_times else None
        
        # 3️⃣ 개선 트렌드 계산 (최근 5개 vs 이전 5개)
        improvement_trend = None
        if len(lap_times) >= 10:
            recent_5 = lap_times[:5]
            previous_5 = lap_times[5:10]
            recent_avg = sum(recent_5) / len(recent_5)
            previous_avg = sum(previous_5) / len(previous_5)
            improvement_trend = previous_avg - recent_avg  # 양수면 개선

        # 4️⃣ 최근 랩 상세 정보 (최대 5개)
        recent_laps_detailed = []
        for lap in recent_laps.data[:5]:
            lap_id = lap["id"]
            try:
                # 섹터 분석
                lap_data = fetch_lap_meta_and_data(lap_id)
                if lap_data:
                    controls_df = pd.DataFrame(lap_data["controls"])
                    controls_df.columns = [c.strip().lower() for c in controls_df.columns]
                    sector_results = get_sector_summary_by_lap_id(supabase, lap_id, controls_df)
                    
                    recent_laps_detailed.append({
                        "lap_id": lap_id,
                        "track": lap["track"],
                        "car": lap["car"],
                        "lap_time": lap["lap_time"],
                        "created_at": lap["created_at"],
                        "weather": lap.get("weather"),
                        "air_temp": lap.get("air_temp"),
                        "track_temp": lap.get("track_temp"),
                        "sector_count": len(sector_results),
                        "sectors": sector_results[:3]  # 처음 3개 섹터만
                    })
            except Exception as e:
                print(f"❌ 랩 {lap_id} 상세 분석 실패: {e}")
                continue

        # 5️⃣ 트랙별 리더보드 (같은 트랙의 최고 기록들)
        track_leaderboard = []
        if track:
            leaderboard_query = supabase.table("lap_meta").select("user_id, lap_time, car, created_at").eq("track", track.lower()).not_.is_("lap_time", "null").order("lap_time", desc=False).limit(10).execute()
            track_leaderboard = leaderboard_query.data or []

        return sanitize_for_json({
            "user_id": user_id,
            "track": track,
            "period_days": days,
            "total_laps": len(recent_laps.data),
            "summary": {
                "best_lap_time": round(best_lap_time, 3) if best_lap_time else None,
                "average_lap_time": round(avg_lap_time, 3) if avg_lap_time else None,
                "improvement_trend": round(improvement_trend, 3) if improvement_trend else None,
                "total_distance": sum([lap.get("lap_time", 0) * 100 for lap in recent_laps.data])  # 대략적 거리
            },
            "recent_laps": recent_laps_detailed,
            "performance_metrics": {
                "consistency_score": _calculate_consistency_score(lap_times),
                "improvement_rate": _calculate_improvement_rate(lap_times),
                "best_sector_times": _get_best_sector_times(user_id, track, days)
            },
            "track_leaderboard": track_leaderboard
        })

    except Exception as e:
        print(f"❌ 대시보드 개요 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"대시보드 데이터 조회 실패: {str(e)}")

@router.get("/dashboard/lap-detail/{lap_id}")
async def get_lap_dashboard_detail(lap_id: str):
    """
    특정 랩의 대시보드용 상세 분석
    - 브레이킹 분석 요약
    - 코너별 성능
    - 시각화 데이터
    """
    try:
        # 1️⃣ 랩 기본 정보
        lap_data = fetch_lap_meta_and_data(lap_id)
        if not lap_data:
            raise HTTPException(status_code=404, detail="랩 데이터를 찾을 수 없습니다.")

        controls = lap_data["controls"]
        vehicle = lap_data["vehicle"]
        meta = lap_data["meta"]

        # 2️⃣ DataFrame 준비
        df_controls = pd.DataFrame(controls)
        df_vehicle = pd.DataFrame(vehicle)
        df_controls.columns = [c.strip().lower() for c in df_controls.columns]
        df_vehicle.columns = [c.strip().lower() for c in df_vehicle.columns]
        df = pd.merge(df_controls, df_vehicle, on="time", how="inner")

        # 3️⃣ 섹터 분석
        sector_results = get_sector_summary_by_lap_id(supabase, lap_id, df_controls)

        # 4️⃣ 브레이킹 분석
        track_name = meta.get("track", "").lower()
        segments = get_corner_segments_for_track(supabase, track_name)
        brake_results = analyze_braking_dynamics(df, segments)
        
        # 5️⃣ 핵심 지표 계산
        performance_metrics = _calculate_lap_performance_metrics(df, brake_results, sector_results)

        # 6️⃣ 시각화용 데이터 준비
        visualization_data = _prepare_visualization_data(df, brake_results, sector_results)

        return sanitize_for_json({
            "lap_id": lap_id,
            "meta": meta,
            "performance_metrics": performance_metrics,
            "sector_analysis": sector_results,
            "braking_analysis": {
                "segments": brake_results.get("segments", []),
                "summary": brake_results.get("summary", {})
            },
            "visualization_data": visualization_data,
            "insights": _generate_lap_insights(performance_metrics, brake_results, sector_results)
        })

    except Exception as e:
        print(f"❌ 랩 상세 분석 실패: {e}")
        raise HTTPException(status_code=500, detail=f"랩 분석 실패: {str(e)}")

@router.get("/dashboard/performance-trends/{user_id}")
async def get_performance_trends(
    user_id: str,
    track: Optional[str] = Query(None),
    days: int = Query(30)
):
    """
    성능 트렌드 분석
    - 시간별 랩 타임 변화
    - 섹터별 개선 추이
    - 브레이킹 효율성 변화
    """
    try:
        date_filter = datetime.now() - timedelta(days=days)
        
        query = supabase.table("lap_meta").select("*").eq("user_id", user_id)
        if track:
            query = query.eq("track", track.lower())
        
        laps = query.gte("created_at", date_filter.isoformat()).order("created_at", desc=False).execute()
        
        if not laps.data:
            return {"trends": [], "insights": []}

        # 트렌드 데이터 생성
        trends = []
        for lap in laps.data:
            if lap["lap_time"]:
                trends.append({
                    "date": lap["created_at"][:10],  # YYYY-MM-DD
                    "lap_time": lap["lap_time"],
                    "track": lap["track"],
                    "car": lap["car"]
                })

        return sanitize_for_json({
            "user_id": user_id,
            "track": track,
            "period_days": days,
            "trends": trends,
            "insights": _analyze_performance_trends(trends)
        })

    except Exception as e:
        print(f"❌ 성능 트렌드 분석 실패: {e}")
        raise HTTPException(status_code=500, detail=f"트렌드 분석 실패: {str(e)}")

# 🔧 헬퍼 함수들

def _calculate_consistency_score(lap_times: List[float]) -> float:
    """랩 타임 일관성 점수 계산 (0-100)"""
    if len(lap_times) < 2:
        return 0.0
    
    mean_time = sum(lap_times) / len(lap_times)
    variance = sum((t - mean_time) ** 2 for t in lap_times) / len(lap_times)
    std_dev = variance ** 0.5
    
    # 표준편차가 작을수록 높은 점수 (최대 100점)
    consistency = max(0, 100 - (std_dev / mean_time * 100))
    return round(consistency, 1)

def _calculate_improvement_rate(lap_times: List[float]) -> float:
    """개선율 계산 (최근 vs 초기)"""
    if len(lap_times) < 4:
        return 0.0
    
    recent_avg = sum(lap_times[:len(lap_times)//2]) / (len(lap_times)//2)
    early_avg = sum(lap_times[len(lap_times)//2:]) / (len(lap_times) - len(lap_times)//2)
    
    improvement = (early_avg - recent_avg) / early_avg * 100
    return round(improvement, 1)

def _get_best_sector_times(user_id: str, track: Optional[str], days: int) -> List[Dict]:
    """최고 섹터 타임 조회"""
    try:
        date_filter = datetime.now() - timedelta(days=days)
        
        # 섹터 결과에서 최고 기록들 조회
        query = supabase.table("sector_results").select("sector_index, sector_time, lap_id")
        query = query.eq("user_id", user_id)
        if track:
            query = query.eq("track", track.lower())
        
        sectors = query.gte("created_at", date_filter.isoformat()).execute()
        
        if not sectors.data:
            return []
        
        # 섹터별 최고 기록 찾기
        best_sectors = {}
        for sector in sectors.data:
            sector_idx = sector["sector_index"]
            if sector_idx not in best_sectors or sector["sector_time"] < best_sectors[sector_idx]["sector_time"]:
                best_sectors[sector_idx] = sector
        
        return list(best_sectors.values())
    
    except Exception as e:
        print(f"❌ 최고 섹터 타임 조회 실패: {e}")
        return []

def _calculate_lap_performance_metrics(df: pd.DataFrame, brake_results: Dict, sector_results: List[Dict]) -> Dict:
    """랩 성능 지표 계산"""
    try:
        # 기본 지표
        total_time = df["time"].iloc[-1] - df["time"].iloc[0]
        avg_speed = df["speed"].mean()
        max_speed = df["speed"].max()
        
        # 브레이킹 지표
        brake_segments = brake_results.get("segments", [])
        total_brake_time = sum(seg.get("duration", 0) for seg in brake_segments)
        brake_efficiency = (total_brake_time / total_time * 100) if total_time > 0 else 0
        
        # 섹터 지표
        sector_times = [s["best_time"] for s in sector_results if "best_time" in s]
        avg_sector_time = sum(sector_times) / len(sector_times) if sector_times else 0
        
        return {
            "total_time": round(total_time, 3),
            "average_speed": round(avg_speed, 1),
            "max_speed": round(max_speed, 1),
            "brake_efficiency": round(brake_efficiency, 1),
            "sector_count": len(sector_results),
            "avg_sector_time": round(avg_sector_time, 3),
            "brake_segments_count": len(brake_segments)
        }
    
    except Exception as e:
        print(f"❌ 성능 지표 계산 실패: {e}")
        return {}

def _prepare_visualization_data(df: pd.DataFrame, brake_results: Dict, sector_results: List[Dict]) -> Dict:
    """시각화용 데이터 준비"""
    try:
        # 기본 그래프 데이터
        graph_keys = [
            "time", "distance", "speed", "throttle", "brake", "steerangle", "gear",
            "g_lon", "g_lat", "abs"
        ]
        available_keys = [k for k in graph_keys if k in df.columns]
        graph_data = df[available_keys].to_dict(orient="records")
        
        # 브레이킹 구간 마킹
        brake_segments = brake_results.get("segments", [])
        for segment in brake_segments:
            start_time = segment.get("start_time")
            end_time = segment.get("end_time")
            if start_time and end_time:
                # 해당 시간대의 데이터에 브레이킹 마크 추가
                for data_point in graph_data:
                    if start_time <= data_point.get("time", 0) <= end_time:
                        data_point["is_braking"] = True
        
        return {
            "graph_data": graph_data,
            "brake_segments": brake_segments,
            "sector_markers": sector_results
        }
    
    except Exception as e:
        print(f"❌ 시각화 데이터 준비 실패: {e}")
        return {"graph_data": [], "brake_segments": [], "sector_markers": []}

def _generate_lap_insights(metrics: Dict, brake_results: Dict, sector_results: List[Dict]) -> List[str]:
    """랩 인사이트 생성"""
    insights = []
    
    try:
        # 브레이킹 인사이트
        brake_segments = brake_results.get("segments", [])
        if brake_segments:
            avg_brake_peak = sum(seg.get("brake_peak", 0) for seg in brake_segments) / len(brake_segments)
            if avg_brake_peak > 80:
                insights.append("브레이킹 강도가 높습니다. 더 부드러운 브레이킹을 시도해보세요.")
            elif avg_brake_peak < 50:
                insights.append("브레이킹이 부족할 수 있습니다. 더 확실한 제동을 시도해보세요.")
        
        # 속도 인사이트
        if metrics.get("max_speed", 0) > 200:
            insights.append("고속 구간에서 좋은 성능을 보였습니다.")
        
        # 일관성 인사이트
        if metrics.get("brake_efficiency", 0) > 30:
            insights.append("브레이킹 시간이 전체 랩의 30% 이상입니다. 더 효율적인 라인을 고려해보세요.")
        
        if not insights:
            insights.append("전반적으로 안정적인 주행을 보였습니다.")
    
    except Exception as e:
        print(f"❌ 인사이트 생성 실패: {e}")
        insights = ["분석 결과를 확인해주세요."]
    
    return insights

def _analyze_performance_trends(trends: List[Dict]) -> List[str]:
    """성능 트렌드 분석"""
    insights = []
    
    try:
        if len(trends) < 3:
            return ["더 많은 데이터가 필요합니다."]
        
        # 최근 3개 vs 이전 3개 비교
        recent_3 = [t["lap_time"] for t in trends[-3:]]
        previous_3 = [t["lap_time"] for t in trends[-6:-3]] if len(trends) >= 6 else []
        
        if previous_3:
            recent_avg = sum(recent_3) / len(recent_3)
            previous_avg = sum(previous_3) / len(previous_3)
            improvement = previous_avg - recent_avg
            
            if improvement > 0.5:
                insights.append(f"최근 {improvement:.1f}초 개선되었습니다! 🎉")
            elif improvement < -0.5:
                insights.append("최근 성능이 다소 하락했습니다. 컨디션을 점검해보세요.")
            else:
                insights.append("성능이 안정적으로 유지되고 있습니다.")
        
        # 일관성 분석
        all_times = [t["lap_time"] for t in trends]
        if len(all_times) > 5:
            std_dev = (sum((t - sum(all_times)/len(all_times))**2 for t in all_times) / len(all_times))**0.5
            if std_dev < 1.0:
                insights.append("매우 일관된 성능을 보이고 있습니다.")
            elif std_dev > 3.0:
                insights.append("성능 편차가 큽니다. 더 안정적인 주행을 연습해보세요.")
    
    except Exception as e:
        print(f"❌ 트렌드 분석 실패: {e}")
        insights = ["트렌드 분석 중 오류가 발생했습니다."]
    
    return insights
