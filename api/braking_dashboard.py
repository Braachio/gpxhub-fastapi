from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
import pandas as pd
from typing import List, Dict, Optional

from utils.supabase_client import supabase
from utils.sanitize import sanitize_for_json
from services.braking_dynamics import analyze_braking_dynamics
from services.brake_feedback import generate_braking_feedback
from services.track_corners import get_corner_segments_for_track
from services.preprocessing import preprocess_csv_data

router = APIRouter()

@router.get("/braking/analysis/{lap_id}")
async def get_braking_analysis_dashboard(lap_id: str):
    """
    브레이킹 분석 대시보드용 데이터
    - 시각화 친화적 데이터 구조
    - 개선 제안 포함
    - 비교 분석 데이터
    """
    try:
        # 1️⃣ 랩 메타데이터 조회
        lap_meta_response = supabase.table("lap_meta").select("*").eq("id", lap_id).execute()
        meta = lap_meta_response.data[0] if lap_meta_response.data else None
        if not meta:
            raise HTTPException(status_code=404, detail="랩 데이터를 찾을 수 없습니다.")
        track = meta.get("track", "").lower()
        user_id = meta.get("user_id")
        
        # 2️⃣ 랩 데이터 조회
        from services.lap_data import fetch_lap_meta_and_data
        lap_data = fetch_lap_meta_and_data(lap_id)
        if not lap_data:
            raise HTTPException(status_code=404, detail="랩 상세 데이터를 찾을 수 없습니다.")
        
        # 3️⃣ DataFrame 준비
        controls_df = pd.DataFrame(lap_data["controls"])
        vehicle_df = pd.DataFrame(lap_data["vehicle"])
        controls_df.columns = [c.strip().lower() for c in controls_df.columns]
        vehicle_df.columns = [c.strip().lower() for c in vehicle_df.columns]
        
        # distance 컬럼 중복 제거 (controls에 distance가 있으면 vehicle의 distance 제거)
        if 'distance' in controls_df.columns and 'distance' in vehicle_df.columns:
            vehicle_df = vehicle_df.drop('distance', axis=1)
        
        df = pd.merge(controls_df, vehicle_df, on="time", how="inner")

        # time 숫자화 및 정렬
        if "time" in df.columns:
            df["time"] = pd.to_numeric(df["time"], errors="coerce").fillna(method="ffill").fillna(0)
        df = df.sort_values("time").reset_index(drop=True)

        # distance가 없으면 time 기반으로 생성 (speed가 있으면 적분, 없으면 인덱스 기반)
        if "distance" not in df.columns:
            print("⚠️ distance 컬럼이 없어 time 기반으로 생성합니다.")
            if "speed" in df.columns:
                dt = df["time"].diff().fillna(0)
                df["distance"] = (pd.to_numeric(df["speed"], errors="coerce").fillna(0) * dt).cumsum()
            else:
                df["distance"] = range(len(df))

        # 필수 컬럼 확인 및 누락된 컬럼 처리 (distance는 위에서 보장)
        required_cols = ["time", "speed", "brake", "steerangle", "abs", "g_lon", "g_lat"]
        missing_cols = [col for col in required_cols if col not in df.columns]

        if missing_cols:
            print(f"⚠️ 누락된 컬럼들: {missing_cols}")
            for col in missing_cols:
                df[col] = 0.0
        
        # 4️⃣ 트랙 세그먼트 로드
        segments = get_corner_segments_for_track(supabase, track)
        
        # 5️⃣ 브레이킹 동역학 분석
        print(f"🔍 API에서 분석할 DataFrame 정보:")
        print(f"  - 컬럼 수: {len(df.columns)}")
        print(f"  - 행 수: {len(df)}")
        print(f"  - distance 컬럼 존재: {'distance' in df.columns}")
        print(f"  - 실제 컬럼들: {list(df.columns)[:10]}...")  # 처음 10개 컬럼만 출력
        print(f"  - 필수 컬럼들: time={'time' in df.columns}, distance={'distance' in df.columns}, speed={'speed' in df.columns}, brake={'brake' in df.columns}")
        
        # distance 컬럼은 braking_dynamics.py에서 자동 생성됨
        
        brake_results = analyze_braking_dynamics(df, segments)
        brake_segments = brake_results.get("segments", [])
        brake_summary = brake_results.get("summary", {})
        
        # 6️⃣ 브레이킹 피드백 생성
        feedbacks = generate_braking_feedback(lap_id, track)
        
        # 7️⃣ UI 친화적 데이터 구조로 변환
        dashboard_data = _format_braking_dashboard_data(
            brake_segments, brake_summary, feedbacks, track, user_id
        )
        
        # 8️⃣ 비교 분석 데이터 추가
        comparison_data = _get_braking_comparison_data(track, user_id, brake_segments)
        
        return sanitize_for_json({
            "lap_id": lap_id,
            "track": track,
            "meta": meta,
            "braking_analysis": dashboard_data,
            "comparison": comparison_data,
            "insights": _generate_braking_insights(brake_segments, brake_summary, feedbacks)
        })
        
    except Exception as e:
        print(f"❌ 브레이킹 분석 대시보드 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"브레이킹 분석 실패: {str(e)}")

@router.get("/braking/comparison/{user_id}")
async def get_braking_comparison(
    user_id: str,
    track: Optional[str] = Query(None),
    days: int = Query(30)
):
    """
    사용자의 브레이킹 성능 비교 분석
    - 시간대별 브레이킹 개선 추이
    - 트랙별 브레이킹 패턴 비교
    - 개선 포인트 제안
    """
    try:
        from datetime import datetime, timedelta
        
        # 1️⃣ 최근 랩들의 브레이킹 분석 데이터 조회
        date_filter = datetime.now() - timedelta(days=days)
        
        query = supabase.table("brake_analysis").select("*").eq("driver_id", user_id)
        if track:
            query = query.eq("track", track.lower())
        
        brake_analyses = query.gte("created_at", date_filter.isoformat()).order("created_at", desc=True).execute()
        
        if not brake_analyses.data:
            return {
                "user_id": user_id,
                "track": track,
                "period_days": days,
                "comparison_data": [],
                "trends": {},
                "recommendations": []
            }
        
        # 2️⃣ 브레이킹 성능 트렌드 분석
        trends = _analyze_braking_trends(brake_analyses.data)
        
        # 3️⃣ 개선 추천 생성
        recommendations = _generate_braking_recommendations(brake_analyses.data, trends)
        
        # 4️⃣ 코너별 성능 비교
        corner_comparison = _get_corner_performance_comparison(brake_analyses.data)
        
        return sanitize_for_json({
            "user_id": user_id,
            "track": track,
            "period_days": days,
            "total_analyses": len(brake_analyses.data),
            "trends": trends,
            "corner_comparison": corner_comparison,
            "recommendations": recommendations
        })
        
    except Exception as e:
        print(f"❌ 브레이킹 비교 분석 실패: {e}")
        raise HTTPException(status_code=500, detail=f"비교 분석 실패: {str(e)}")

@router.get("/braking/leaderboard/{track}")
async def get_braking_leaderboard(track: str, corner_index: Optional[int] = Query(None)):
    """
    트랙별 브레이킹 리더보드
    - 코너별 최고 브레이킹 성능
    - 평균 브레이킹 타이밍
    - 베스트 프랙티스
    """
    try:
        # 1️⃣ 트랙의 브레이킹 분석 데이터 조회
        query = supabase.table("brake_analysis").select("*").eq("track", track.lower())
        if corner_index is not None:
            query = query.eq("corner_index", corner_index)
        
        brake_data = query.order("created_at", desc=True).limit(100).execute()
        
        if not brake_data.data:
            return {
                "track": track,
                "corner_index": corner_index,
                "leaderboard": [],
                "statistics": {}
            }
        
        # 2️⃣ 리더보드 생성
        leaderboard = _create_braking_leaderboard(brake_data.data, corner_index)
        
        # 3️⃣ 통계 데이터 생성
        statistics = _calculate_braking_statistics(brake_data.data, corner_index)
        
        return sanitize_for_json({
            "track": track,
            "corner_index": corner_index,
            "leaderboard": leaderboard,
            "statistics": statistics,
            "best_practices": _extract_best_practices(brake_data.data)
        })
        
    except Exception as e:
        print(f"❌ 브레이킹 리더보드 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"리더보드 조회 실패: {str(e)}")

# 🔧 헬퍼 함수들

def _format_braking_dashboard_data(
    brake_segments: List[Dict], 
    brake_summary: Dict, 
    feedbacks: List[str], 
    track: str, 
    user_id: str
) -> Dict:
    """브레이킹 분석 데이터를 UI 친화적으로 포맷팅"""
    
    # 시각화용 데이터 준비
    visualization_data = {
        "brake_zones": [],
        "performance_metrics": [],
        "corner_analysis": []
    }
    
    for i, segment in enumerate(brake_segments):
        # 브레이킹 존 데이터
        brake_zone = {
            "id": f"brake_zone_{i}",
            "corner_index": segment.get("corner_index", i),
            "segment_name": segment.get("segment_name", f"코너 {i+1}"),
            "start_time": segment.get("start_time"),
            "end_time": segment.get("end_time"),
            "start_distance": segment.get("start_distance"),
            "end_distance": segment.get("end_distance"),
            "duration": segment.get("duration"),
            "brake_peak": segment.get("brake_peak"),
            "decel_avg": segment.get("decel_avg"),
            "trail_braking_ratio": segment.get("trail_braking_ratio"),
            "abs_on_ratio": segment.get("abs_on_ratio"),
            "slip_lock_ratio_front": segment.get("slip_lock_ratio_front"),
            "slip_lock_ratio_rear": segment.get("slip_lock_ratio_rear")
        }
        visualization_data["brake_zones"].append(brake_zone)
        
        # 성능 지표
        performance_metric = {
            "corner_index": segment.get("corner_index", i),
            "brake_efficiency": _calculate_brake_efficiency(segment),
            "smoothness_score": _calculate_smoothness_score(segment),
            "aggressiveness_score": _calculate_aggressiveness_score(segment)
        }
        visualization_data["performance_metrics"].append(performance_metric)
        
        # 코너별 분석
        corner_analysis = {
            "corner_index": segment.get("corner_index", i),
            "segment_name": segment.get("segment_name", f"코너 {i+1}"),
            "strengths": _identify_braking_strengths(segment),
            "weaknesses": _identify_braking_weaknesses(segment),
            "improvement_areas": _suggest_improvements(segment)
        }
        visualization_data["corner_analysis"].append(corner_analysis)
    
    return {
        "summary": {
            "total_brake_zones": len(brake_segments),
            "average_brake_peak": brake_summary.get("avg_brake_peak", 0),
            "average_deceleration": brake_summary.get("avg_decel", 0),
            "trail_braking_usage": brake_summary.get("avg_trail_ratio", 0),
            "abs_usage": brake_summary.get("avg_abs_on_ratio", 0)
        },
        "visualization": visualization_data,
        "feedbacks": feedbacks,
        "overall_score": _calculate_overall_braking_score(brake_segments, brake_summary)
    }

def _get_braking_comparison_data(track: str, user_id: str, current_segments: List[Dict]) -> Dict:
    """브레이킹 비교 분석 데이터"""
    try:
        # 같은 트랙의 다른 사용자들 데이터 조회
        comparison_query = supabase.table("brake_analysis").select("*").eq("track", track.lower()).neq("driver_id", user_id).limit(50).execute()
        
        if not comparison_query.data:
            return {"benchmark_data": [], "comparison_metrics": {}}
        
        # 벤치마크 데이터 생성
        benchmark_data = []
        for segment in current_segments:
            corner_idx = segment.get("corner_index")
            if corner_idx is not None:
                # 같은 코너의 다른 사용자들 데이터
                corner_data = [s for s in comparison_query.data if s.get("corner_index") == corner_idx]
                if corner_data:
                    avg_brake_peak = sum(s.get("brake_peak", 0) for s in corner_data) / len(corner_data)
                    avg_decel = sum(s.get("decel_avg", 0) for s in corner_data) / len(corner_data)
                    
                    benchmark_data.append({
                        "corner_index": corner_idx,
                        "segment_name": segment.get("segment_name", f"코너 {corner_idx+1}"),
                        "your_brake_peak": segment.get("brake_peak", 0),
                        "benchmark_brake_peak": avg_brake_peak,
                        "your_decel": segment.get("decel_avg", 0),
                        "benchmark_decel": avg_decel,
                        "performance_vs_benchmark": _compare_performance(segment, corner_data)
                    })
        
        return {
            "benchmark_data": benchmark_data,
            "comparison_metrics": _calculate_comparison_metrics(current_segments, comparison_query.data)
        }
        
    except Exception as e:
        print(f"❌ 브레이킹 비교 데이터 생성 실패: {e}")
        return {"benchmark_data": [], "comparison_metrics": {}}

def _generate_braking_insights(segments: List[Dict], summary: Dict, feedbacks: List[str]) -> List[Dict]:
    """브레이킹 인사이트 생성"""
    insights = []
    
    try:
        # 전체 성능 인사이트
        if summary.get("avg_brake_peak", 0) > 80:
            insights.append({
                "type": "warning",
                "title": "강한 브레이킹",
                "message": "평균 브레이킹 강도가 높습니다. 더 부드러운 제동을 시도해보세요.",
                "priority": "high"
            })
        
        if summary.get("avg_abs_on_ratio", 0) > 0.3:
            insights.append({
                "type": "info",
                "title": "ABS 사용률 높음",
                "message": "ABS가 자주 작동하고 있습니다. 브레이킹 타이밍을 조정해보세요.",
                "priority": "medium"
            })
        
        if summary.get("avg_trail_ratio", 0) > 0.5:
            insights.append({
                "type": "success",
                "title": "트레일 브레이킹 활용",
                "message": "트레일 브레이킹을 잘 활용하고 있습니다!",
                "priority": "low"
            })
        
        # 코너별 인사이트
        for segment in segments:
            corner_idx = segment.get("corner_index")
            if corner_idx is not None:
                if segment.get("slip_lock_ratio_front", 0) > 0.2:
                    insights.append({
                        "type": "warning",
                        "title": f"코너 {corner_idx+1} 프론트 슬립",
                        "message": "프론트 타이어 슬립이 발생하고 있습니다.",
                        "priority": "high",
                        "corner_index": corner_idx
                    })
        
        # 피드백 기반 인사이트
        for feedback in feedbacks:
            if "빠르게" in feedback:
                insights.append({
                    "type": "info",
                    "title": "브레이킹 타이밍",
                    "message": feedback,
                    "priority": "medium"
                })
        
        if not insights:
            insights.append({
                "type": "success",
                "title": "안정적인 브레이킹",
                "message": "전반적으로 안정적인 브레이킹 패턴을 보이고 있습니다.",
                "priority": "low"
            })
        
    except Exception as e:
        print(f"❌ 브레이킹 인사이트 생성 실패: {e}")
        insights = [{
            "type": "info",
            "title": "분석 중",
            "message": "브레이킹 분석 결과를 확인해주세요.",
            "priority": "low"
        }]
    
    return insights

def _analyze_braking_trends(brake_data: List[Dict]) -> Dict:
    """브레이킹 트렌드 분석"""
    try:
        if len(brake_data) < 3:
            return {"trend": "insufficient_data", "change_rate": 0}
        
        # 시간순 정렬
        sorted_data = sorted(brake_data, key=lambda x: x.get("created_at", ""))
        
        # 최근 vs 초기 성능 비교
        recent_data = sorted_data[-len(sorted_data)//3:]  # 최근 1/3
        early_data = sorted_data[:len(sorted_data)//3]    # 초기 1/3
        
        recent_avg_peak = sum(d.get("brake_peak", 0) for d in recent_data) / len(recent_data)
        early_avg_peak = sum(d.get("brake_peak", 0) for d in early_data) / len(early_data)
        
        change_rate = (recent_avg_peak - early_avg_peak) / early_avg_peak * 100 if early_avg_peak > 0 else 0
        
        trend = "improving" if change_rate < -5 else "declining" if change_rate > 5 else "stable"
        
        return {
            "trend": trend,
            "change_rate": round(change_rate, 1),
            "recent_performance": round(recent_avg_peak, 1),
            "early_performance": round(early_avg_peak, 1)
        }
        
    except Exception as e:
        print(f"❌ 브레이킹 트렌드 분석 실패: {e}")
        return {"trend": "error", "change_rate": 0}

def _generate_braking_recommendations(brake_data: List[Dict], trends: Dict) -> List[Dict]:
    """브레이킹 개선 추천 생성"""
    recommendations = []
    
    try:
        # 트렌드 기반 추천
        if trends.get("trend") == "declining":
            recommendations.append({
                "type": "improvement",
                "title": "브레이킹 성능 하락",
                "description": "최근 브레이킹 성능이 하락하고 있습니다. 기본기 연습을 권장합니다.",
                "priority": "high"
            })
        
        # 데이터 기반 추천
        avg_abs_usage = sum(d.get("abs_on_ratio", 0) for d in brake_data) / len(brake_data)
        if avg_abs_usage > 0.3:
            recommendations.append({
                "type": "technique",
                "title": "ABS 사용률 감소",
                "description": "ABS 사용률이 높습니다. 더 부드러운 브레이킹을 연습해보세요.",
                "priority": "medium"
            })
        
        avg_trail_usage = sum(d.get("trail_braking_ratio", 0) for d in brake_data) / len(brake_data)
        if avg_trail_usage < 0.3:
            recommendations.append({
                "type": "technique",
                "title": "트레일 브레이킹 활용",
                "description": "트레일 브레이킹을 더 활용하면 코너 진입이 부드러워집니다.",
                "priority": "medium"
            })
        
        if not recommendations:
            recommendations.append({
                "type": "maintenance",
                "title": "현재 상태 유지",
                "description": "브레이킹 성능이 안정적입니다. 현재 패턴을 유지하세요.",
                "priority": "low"
            })
        
    except Exception as e:
        print(f"❌ 브레이킹 추천 생성 실패: {e}")
        recommendations = [{
            "type": "info",
            "title": "분석 중",
            "description": "추천 사항을 분석 중입니다.",
            "priority": "low"
        }]
    
    return recommendations

def _get_corner_performance_comparison(brake_data: List[Dict]) -> List[Dict]:
    """코너별 성능 비교"""
    try:
        # 코너별 데이터 그룹화
        corner_groups = {}
        for data in brake_data:
            corner_idx = data.get("corner_index")
            if corner_idx is not None:
                if corner_idx not in corner_groups:
                    corner_groups[corner_idx] = []
                corner_groups[corner_idx].append(data)
        
        comparison = []
        for corner_idx, data_list in corner_groups.items():
            if len(data_list) > 1:
                avg_peak = sum(d.get("brake_peak", 0) for d in data_list) / len(data_list)
                avg_decel = sum(d.get("decel_avg", 0) for d in data_list) / len(data_list)
                consistency = _calculate_consistency(data_list)
                
                comparison.append({
                    "corner_index": corner_idx,
                    "segment_name": data_list[0].get("segment_name", f"코너 {corner_idx+1}"),
                    "average_brake_peak": round(avg_peak, 1),
                    "average_deceleration": round(avg_decel, 1),
                    "consistency_score": round(consistency, 1),
                    "sample_count": len(data_list)
                })
        
        return sorted(comparison, key=lambda x: x["corner_index"])
        
    except Exception as e:
        print(f"❌ 코너 성능 비교 실패: {e}")
        return []

def _create_braking_leaderboard(brake_data: List[Dict], corner_index: Optional[int]) -> List[Dict]:
    """브레이킹 리더보드 생성"""
    try:
        # 필터링
        filtered_data = brake_data
        if corner_index is not None:
            filtered_data = [d for d in brake_data if d.get("corner_index") == corner_index]
        
        # 성능 점수 계산 및 정렬
        scored_data = []
        for data in filtered_data:
            score = _calculate_braking_score(data)
            scored_data.append({
                "driver_id": data.get("driver_id"),
                "lap_id": data.get("lap_id"),
                "corner_index": data.get("corner_index"),
                "segment_name": data.get("segment_name"),
                "brake_peak": data.get("brake_peak", 0),
                "decel_avg": data.get("decel_avg", 0),
                "trail_braking_ratio": data.get("trail_braking_ratio", 0),
                "abs_on_ratio": data.get("abs_on_ratio", 0),
                "performance_score": score,
                "created_at": data.get("created_at")
            })
        
        # 점수순 정렬 (높은 점수가 좋음)
        leaderboard = sorted(scored_data, key=lambda x: x["performance_score"], reverse=True)[:20]
        
        return leaderboard
        
    except Exception as e:
        print(f"❌ 브레이킹 리더보드 생성 실패: {e}")
        return []

def _calculate_braking_statistics(brake_data: List[Dict], corner_index: Optional[int]) -> Dict:
    """브레이킹 통계 계산"""
    try:
        filtered_data = brake_data
        if corner_index is not None:
            filtered_data = [d for d in brake_data if d.get("corner_index") == corner_index]
        
        if not filtered_data:
            return {}
        
        brake_peaks = [d.get("brake_peak", 0) for d in filtered_data]
        decels = [d.get("decel_avg", 0) for d in filtered_data]
        trail_ratios = [d.get("trail_braking_ratio", 0) for d in filtered_data]
        abs_ratios = [d.get("abs_on_ratio", 0) for d in filtered_data]
        
        return {
            "total_samples": len(filtered_data),
            "brake_peak": {
                "average": round(sum(brake_peaks) / len(brake_peaks), 1),
                "min": round(min(brake_peaks), 1),
                "max": round(max(brake_peaks), 1)
            },
            "deceleration": {
                "average": round(sum(decels) / len(decels), 1),
                "min": round(min(decels), 1),
                "max": round(max(decels), 1)
            },
            "trail_braking": {
                "average_usage": round(sum(trail_ratios) / len(trail_ratios), 2),
                "max_usage": round(max(trail_ratios), 2)
            },
            "abs_usage": {
                "average_usage": round(sum(abs_ratios) / len(abs_ratios), 2),
                "max_usage": round(max(abs_ratios), 2)
            }
        }
        
    except Exception as e:
        print(f"❌ 브레이킹 통계 계산 실패: {e}")
        return {}

def _extract_best_practices(brake_data: List[Dict]) -> List[Dict]:
    """베스트 프랙티스 추출"""
    try:
        # 상위 10% 성능 데이터에서 패턴 추출
        scored_data = [(d, _calculate_braking_score(d)) for d in brake_data]
        scored_data.sort(key=lambda x: x[1], reverse=True)
        
        top_10_percent = scored_data[:max(1, len(scored_data) // 10)]
        
        best_practices = []
        if top_10_percent:
            avg_brake_peak = sum(d[0].get("brake_peak", 0) for d in top_10_percent) / len(top_10_percent)
            avg_trail_ratio = sum(d[0].get("trail_braking_ratio", 0) for d in top_10_percent) / len(top_10_percent)
            avg_abs_ratio = sum(d[0].get("abs_on_ratio", 0) for d in top_10_percent) / len(top_10_percent)
            
            best_practices = [
                {
                    "practice": "브레이킹 강도",
                    "recommended_value": round(avg_brake_peak, 1),
                    "description": f"상위 성능자들의 평균 브레이킹 강도는 {avg_brake_peak:.1f}%입니다."
                },
                {
                    "practice": "트레일 브레이킹",
                    "recommended_value": round(avg_trail_ratio, 2),
                    "description": f"트레일 브레이킹 사용률은 {avg_trail_ratio:.2f}가 효과적입니다."
                },
                {
                    "practice": "ABS 사용",
                    "recommended_value": round(avg_abs_ratio, 2),
                    "description": f"ABS 사용률은 {avg_abs_ratio:.2f} 이하로 유지하는 것이 좋습니다."
                }
            ]
        
        return best_practices
        
    except Exception as e:
        print(f"❌ 베스트 프랙티스 추출 실패: {e}")
        return []

# 🔧 유틸리티 함수들

def _calculate_brake_efficiency(segment: Dict) -> float:
    """브레이킹 효율성 점수 계산 (0-100)"""
    try:
        brake_peak = segment.get("brake_peak", 0)
        decel_avg = segment.get("decel_avg", 0)
        abs_ratio = segment.get("abs_on_ratio", 0)
        
        # 효율성 점수 계산 (ABS 사용률이 낮을수록, 적절한 브레이킹 강도일수록 높은 점수)
        efficiency = 100 - (abs_ratio * 50)  # ABS 사용률에 따른 감점
        if brake_peak > 0:
            efficiency += min(20, (brake_peak - 50) / 2)  # 적절한 브레이킹 강도 보너스
        
        return max(0, min(100, round(efficiency, 1)))
    except:
        return 50.0

def _calculate_smoothness_score(segment: Dict) -> float:
    """브레이킹 부드러움 점수 계산 (0-100)"""
    try:
        abs_ratio = segment.get("abs_on_ratio", 0)
        slip_ratio = max(
            segment.get("slip_lock_ratio_front", 0),
            segment.get("slip_lock_ratio_rear", 0)
        )
        
        # ABS와 슬립 비율이 낮을수록 부드러운 브레이킹
        smoothness = 100 - (abs_ratio * 30) - (slip_ratio * 40)
        return max(0, min(100, round(smoothness, 1)))
    except:
        return 50.0

def _calculate_aggressiveness_score(segment: Dict) -> float:
    """브레이킹 공격성 점수 계산 (0-100)"""
    try:
        brake_peak = segment.get("brake_peak", 0)
        decel_avg = segment.get("decel_avg", 0)
        
        # 브레이킹 강도와 감속률 기반 공격성 점수
        aggressiveness = (brake_peak * 0.6) + (decel_avg * 0.4)
        return max(0, min(100, round(aggressiveness, 1)))
    except:
        return 50.0

def _identify_braking_strengths(segment: Dict) -> List[str]:
    """브레이킹 강점 식별"""
    strengths = []
    
    if segment.get("trail_braking_ratio", 0) > 0.5:
        strengths.append("트레일 브레이킹 활용")
    
    if segment.get("abs_on_ratio", 0) < 0.2:
        strengths.append("부드러운 브레이킹")
    
    if segment.get("brake_peak", 0) > 70:
        strengths.append("확실한 제동")
    
    return strengths if strengths else ["안정적인 브레이킹"]

def _identify_braking_weaknesses(segment: Dict) -> List[str]:
    """브레이킹 약점 식별"""
    weaknesses = []
    
    if segment.get("abs_on_ratio", 0) > 0.4:
        weaknesses.append("ABS 과다 사용")
    
    if segment.get("slip_lock_ratio_front", 0) > 0.3:
        weaknesses.append("프론트 타이어 슬립")
    
    if segment.get("slip_lock_ratio_rear", 0) > 0.3:
        weaknesses.append("리어 타이어 슬립")
    
    return weaknesses

def _suggest_improvements(segment: Dict) -> List[str]:
    """개선 제안 생성"""
    suggestions = []
    
    if segment.get("abs_on_ratio", 0) > 0.3:
        suggestions.append("더 부드러운 브레이킹으로 ABS 사용률 감소")
    
    if segment.get("trail_braking_ratio", 0) < 0.3:
        suggestions.append("트레일 브레이킹 활용으로 코너 진입 개선")
    
    if segment.get("brake_peak", 0) > 85:
        suggestions.append("브레이킹 강도 조절로 타이어 보호")
    
    return suggestions if suggestions else ["현재 패턴 유지"]

def _calculate_overall_braking_score(segments: List[Dict], summary: Dict) -> float:
    """전체 브레이킹 점수 계산 (0-100)"""
    try:
        if not segments:
            return 0.0
        
        # 각 세그먼트의 점수 평균
        segment_scores = []
        for segment in segments:
            efficiency = _calculate_brake_efficiency(segment)
            smoothness = _calculate_smoothness_score(segment)
            score = (efficiency + smoothness) / 2
            segment_scores.append(score)
        
        overall_score = sum(segment_scores) / len(segment_scores)
        return round(overall_score, 1)
    except:
        return 50.0

def _compare_performance(current_segment: Dict, benchmark_data: List[Dict]) -> str:
    """성능 비교 결과"""
    try:
        current_peak = current_segment.get("brake_peak", 0)
        benchmark_avg = sum(d.get("brake_peak", 0) for d in benchmark_data) / len(benchmark_data)
        
        diff = current_peak - benchmark_avg
        if diff > 10:
            return "above_average"
        elif diff < -10:
            return "below_average"
        else:
            return "average"
    except:
        return "unknown"

def _calculate_consistency(data_list: List[Dict]) -> float:
    """일관성 점수 계산"""
    try:
        if len(data_list) < 2:
            return 100.0
        
        brake_peaks = [d.get("brake_peak", 0) for d in data_list]
        mean_peak = sum(brake_peaks) / len(brake_peaks)
        variance = sum((p - mean_peak) ** 2 for p in brake_peaks) / len(brake_peaks)
        std_dev = variance ** 0.5
        
        # 표준편차가 작을수록 높은 일관성 점수
        consistency = max(0, 100 - (std_dev / mean_peak * 100)) if mean_peak > 0 else 100
        return consistency
    except:
        return 50.0

def _calculate_braking_score(data: Dict) -> float:
    """브레이킹 성능 점수 계산"""
    try:
        brake_peak = data.get("brake_peak", 0)
        decel_avg = data.get("decel_avg", 0)
        trail_ratio = data.get("trail_braking_ratio", 0)
        abs_ratio = data.get("abs_on_ratio", 0)
        
        # 점수 계산 (높을수록 좋음)
        score = 0
        score += min(40, brake_peak * 0.4)  # 브레이킹 강도 (최대 40점)
        score += min(30, decel_avg * 0.3)   # 감속률 (최대 30점)
        score += trail_ratio * 20           # 트레일 브레이킹 (최대 20점)
        score += max(0, 10 - abs_ratio * 20)  # ABS 사용률 감점 (최대 10점)
        
        return round(score, 1)
    except:
        return 0.0

def _calculate_comparison_metrics(current_segments: List[Dict], benchmark_data: List[Dict]) -> Dict:
    """비교 지표 계산"""
    try:
        if not current_segments or not benchmark_data:
            return {}
        
        # 현재 성능 평균
        current_avg_peak = sum(s.get("brake_peak", 0) for s in current_segments) / len(current_segments)
        current_avg_decel = sum(s.get("decel_avg", 0) for s in current_segments) / len(current_segments)
        current_avg_trail = sum(s.get("trail_braking_ratio", 0) for s in current_segments) / len(current_segments)
        current_avg_abs = sum(s.get("abs_on_ratio", 0) for s in current_segments) / len(current_segments)
        
        # 벤치마크 평균
        benchmark_avg_peak = sum(d.get("brake_peak", 0) for d in benchmark_data) / len(benchmark_data)
        benchmark_avg_decel = sum(d.get("decel_avg", 0) for d in benchmark_data) / len(benchmark_data)
        benchmark_avg_trail = sum(d.get("trail_braking_ratio", 0) for d in benchmark_data) / len(benchmark_data)
        benchmark_avg_abs = sum(d.get("abs_on_ratio", 0) for d in benchmark_data) / len(benchmark_data)
        
        return {
            "brake_peak": {
                "current": round(current_avg_peak, 1),
                "benchmark": round(benchmark_avg_peak, 1),
                "difference": round(current_avg_peak - benchmark_avg_peak, 1)
            },
            "deceleration": {
                "current": round(current_avg_decel, 1),
                "benchmark": round(benchmark_avg_decel, 1),
                "difference": round(current_avg_decel - benchmark_avg_decel, 1)
            },
            "trail_braking": {
                "current": round(current_avg_trail, 2),
                "benchmark": round(benchmark_avg_trail, 2),
                "difference": round(current_avg_trail - benchmark_avg_trail, 2)
            },
            "abs_usage": {
                "current": round(current_avg_abs, 2),
                "benchmark": round(benchmark_avg_abs, 2),
                "difference": round(current_avg_abs - benchmark_avg_abs, 2)
            }
        }
    except Exception as e:
        print(f"❌ 비교 지표 계산 실패: {e}")
        return {}
