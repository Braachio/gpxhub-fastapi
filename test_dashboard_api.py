#!/usr/bin/env python3
"""
대시보드 API 테스트 스크립트
실시간 대시보드와 브레이킹 분석 API를 테스트합니다.
"""

import requests
import json
from typing import Dict, Any

# API 기본 URL
BASE_URL = "http://localhost:8000/api"

def test_dashboard_overview(user_id: str = "test-user-123", track: str = None, days: int = 30):
    """대시보드 개요 테스트"""
    print("🔍 대시보드 개요 테스트...")
    
    url = f"{BASE_URL}/dashboard/overview/{user_id}"
    params = {}
    if track:
        params["track"] = track
    params["days"] = days
    
    try:
        response = requests.get(url, params=params)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ 대시보드 개요 조회 성공")
            print(f"  - 총 랩 수: {data.get('total_laps', 0)}")
            print(f"  - 최고 랩 타임: {data.get('summary', {}).get('best_lap_time', 'N/A')}")
            print(f"  - 평균 랩 타임: {data.get('summary', {}).get('average_lap_time', 'N/A')}")
            print(f"  - 개선 트렌드: {data.get('summary', {}).get('improvement_trend', 'N/A')}")
            return data
        else:
            print(f"❌ 오류: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ 요청 실패: {e}")
        return None

def test_lap_dashboard_detail(lap_id: str):
    """랩 상세 대시보드 테스트"""
    print(f"🔍 랩 상세 대시보드 테스트 (lap_id: {lap_id})...")
    
    url = f"{BASE_URL}/dashboard/lap-detail/{lap_id}"
    
    try:
        response = requests.get(url)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ 랩 상세 대시보드 조회 성공")
            print(f"  - 트랙: {data.get('meta', {}).get('track', 'N/A')}")
            print(f"  - 차량: {data.get('meta', {}).get('car', 'N/A')}")
            print(f"  - 섹터 수: {len(data.get('sector_analysis', []))}")
            print(f"  - 브레이킹 세그먼트 수: {len(data.get('braking_analysis', {}).get('segments', []))}")
            return data
        else:
            print(f"❌ 오류: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ 요청 실패: {e}")
        return None

def test_performance_trends(user_id: str = "test-user-123", track: str = None, days: int = 30):
    """성능 트렌드 테스트"""
    print("🔍 성능 트렌드 테스트...")
    
    url = f"{BASE_URL}/dashboard/performance-trends/{user_id}"
    params = {}
    if track:
        params["track"] = track
    params["days"] = days
    
    try:
        response = requests.get(url, params=params)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ 성능 트렌드 조회 성공")
            print(f"  - 트렌드 데이터 수: {len(data.get('trends', []))}")
            print(f"  - 인사이트 수: {len(data.get('insights', []))}")
            return data
        else:
            print(f"❌ 오류: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ 요청 실패: {e}")
        return None

def test_braking_analysis_dashboard(lap_id: str):
    """브레이킹 분석 대시보드 테스트"""
    print(f"🔍 브레이킹 분석 대시보드 테스트 (lap_id: {lap_id})...")
    
    url = f"{BASE_URL}/braking/analysis/{lap_id}"
    
    try:
        response = requests.get(url)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ 브레이킹 분석 대시보드 조회 성공")
            
            braking_analysis = data.get('braking_analysis', {})
            summary = braking_analysis.get('summary', {})
            visualization = braking_analysis.get('visualization', {})
            
            print(f"  - 총 브레이킹 존: {summary.get('total_brake_zones', 0)}")
            print(f"  - 평균 브레이킹 강도: {summary.get('average_brake_peak', 0)}")
            print(f"  - 트레일 브레이킹 사용률: {summary.get('trail_braking_usage', 0)}")
            print(f"  - 전체 점수: {braking_analysis.get('overall_score', 0)}")
            print(f"  - 브레이킹 존 수: {len(visualization.get('brake_zones', []))}")
            print(f"  - 인사이트 수: {len(data.get('insights', []))}")
            
            return data
        else:
            print(f"❌ 오류: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ 요청 실패: {e}")
        return None

def test_braking_comparison(user_id: str = "test-user-123", track: str = None, days: int = 30):
    """브레이킹 비교 분석 테스트"""
    print("🔍 브레이킹 비교 분석 테스트...")
    
    url = f"{BASE_URL}/braking/comparison/{user_id}"
    params = {}
    if track:
        params["track"] = track
    params["days"] = days
    
    try:
        response = requests.get(url, params=params)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ 브레이킹 비교 분석 조회 성공")
            print(f"  - 총 분석 수: {data.get('total_analyses', 0)}")
            print(f"  - 트렌드: {data.get('trends', {}).get('trend', 'N/A')}")
            print(f"  - 코너 비교 수: {len(data.get('corner_comparison', []))}")
            print(f"  - 추천 사항 수: {len(data.get('recommendations', []))}")
            return data
        else:
            print(f"❌ 오류: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ 요청 실패: {e}")
        return None

def test_braking_leaderboard(track: str = "test-track", corner_index: int = None):
    """브레이킹 리더보드 테스트"""
    print(f"🔍 브레이킹 리더보드 테스트 (track: {track})...")
    
    url = f"{BASE_URL}/braking/leaderboard/{track}"
    params = {}
    if corner_index is not None:
        params["corner_index"] = corner_index
    
    try:
        response = requests.get(url, params=params)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ 브레이킹 리더보드 조회 성공")
            print(f"  - 리더보드 수: {len(data.get('leaderboard', []))}")
            print(f"  - 통계 데이터: {bool(data.get('statistics', {}))}")
            print(f"  - 베스트 프랙티스 수: {len(data.get('best_practices', []))}")
            return data
        else:
            print(f"❌ 오류: {response.text}")
            return None
            
    except Exception as e:
        print(f"❌ 요청 실패: {e}")
        return None

def run_all_tests():
    """모든 API 테스트 실행"""
    print("🚀 대시보드 API 전체 테스트 시작\n")
    
    # 테스트용 데이터
    test_user_id = "test-user-123"
    test_track = "test-track"
    test_lap_id = "test-lap-456"
    
    # 1. 대시보드 개요 테스트
    print("=" * 50)
    dashboard_overview = test_dashboard_overview(test_user_id, test_track, 30)
    print()
    
    # 2. 성능 트렌드 테스트
    print("=" * 50)
    performance_trends = test_performance_trends(test_user_id, test_track, 30)
    print()
    
    # 3. 랩 상세 대시보드 테스트
    print("=" * 50)
    lap_detail = test_lap_dashboard_detail(test_lap_id)
    print()
    
    # 4. 브레이킹 분석 대시보드 테스트
    print("=" * 50)
    braking_analysis = test_braking_analysis_dashboard(test_lap_id)
    print()
    
    # 5. 브레이킹 비교 분석 테스트
    print("=" * 50)
    braking_comparison = test_braking_comparison(test_user_id, test_track, 30)
    print()
    
    # 6. 브레이킹 리더보드 테스트
    print("=" * 50)
    braking_leaderboard = test_braking_leaderboard(test_track, 0)
    print()
    
    # 결과 요약
    print("=" * 50)
    print("📊 테스트 결과 요약")
    print("=" * 50)
    
    tests = [
        ("대시보드 개요", dashboard_overview is not None),
        ("성능 트렌드", performance_trends is not None),
        ("랩 상세 대시보드", lap_detail is not None),
        ("브레이킹 분석 대시보드", braking_analysis is not None),
        ("브레이킹 비교 분석", braking_comparison is not None),
        ("브레이킹 리더보드", braking_leaderboard is not None)
    ]
    
    passed = sum(1 for _, success in tests if success)
    total = len(tests)
    
    for test_name, success in tests:
        status = "✅ 통과" if success else "❌ 실패"
        print(f"  {test_name}: {status}")
    
    print(f"\n총 {total}개 테스트 중 {passed}개 통과 ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 모든 테스트가 성공적으로 완료되었습니다!")
    else:
        print("⚠️ 일부 테스트가 실패했습니다. 서버 상태를 확인해주세요.")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "overview":
            test_dashboard_overview()
        elif sys.argv[1] == "trends":
            test_performance_trends()
        elif sys.argv[1] == "lap":
            lap_id = sys.argv[2] if len(sys.argv) > 2 else "test-lap-456"
            test_lap_dashboard_detail(lap_id)
        elif sys.argv[1] == "braking":
            lap_id = sys.argv[2] if len(sys.argv) > 2 else "test-lap-456"
            test_braking_analysis_dashboard(lap_id)
        elif sys.argv[1] == "comparison":
            test_braking_comparison()
        elif sys.argv[1] == "leaderboard":
            track = sys.argv[2] if len(sys.argv) > 2 else "test-track"
            test_braking_leaderboard(track)
        else:
            print("사용법: python test_dashboard_api.py [overview|trends|lap|braking|comparison|leaderboard]")
    else:
        run_all_tests()
