#!/usr/bin/env python3
"""
수정된 API 테스트
"""

import requests

def test_braking_api():
    lap_id = '7187305b-0ce8-4f03-94c5-5c9b48130efd'
    url = f"http://localhost:8000/api/braking/analysis/{lap_id}"
    
    try:
        print(f"🔍 API 테스트: {url}")
        response = requests.get(url, timeout=10)
        
        print(f"📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ API 호출 성공!")
            braking_analysis = data.get('braking_analysis', {})
            summary = braking_analysis.get('summary', {})
            print(f"📊 브레이킹 분석 요약:")
            print(f"  - 총 브레이킹 존: {summary.get('total_brake_zones', 0)}")
            print(f"  - 평균 브레이킹 강도: {summary.get('average_brake_peak', 0)}")
            print(f"  - 트레일 브레이킹 사용률: {summary.get('trail_braking_usage', 0)}")
            print(f"  - 전체 점수: {braking_analysis.get('overall_score', 0)}")
        else:
            print(f"❌ API 호출 실패: {response.status_code}")
            print(f"❌ 응답 내용: {response.text}")
            
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

def test_dashboard_api():
    user_id = 'test-user-123'
    url = f"http://localhost:8000/api/dashboard/overview/{user_id}"
    
    try:
        print(f"🔍 대시보드 API 테스트: {url}")
        response = requests.get(url, timeout=10)
        
        print(f"📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ 대시보드 API 호출 성공!")
            print(f"📊 총 랩 수: {data.get('total_laps', 0)}")
        else:
            print(f"❌ 대시보드 API 호출 실패: {response.status_code}")
            print(f"❌ 응답 내용: {response.text}")
            
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    print("🚀 수정된 API 테스트 시작\n")
    
    print("=" * 50)
    test_braking_api()
    
    print("\n" + "=" * 50)
    test_dashboard_api()
    
    print("\n🎉 테스트 완료")

