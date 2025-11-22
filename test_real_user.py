#!/usr/bin/env python3
"""
실제 사용자 ID로 API 테스트
"""

import requests

def test_with_real_user():
    real_user_id = '5eff0b26-a4d3-41a7-8ac7-9a0d32155b22'
    lap_id = '7187305b-0ce8-4f03-94c5-5c9b48130efd'
    
    print("🔍 실제 사용자 ID로 테스트")
    print(f"User ID: {real_user_id}")
    print(f"Lap ID: {lap_id}")
    
    # 1. 브레이킹 분석 API 테스트
    print("\n" + "="*50)
    print("1. 브레이킹 분석 API 테스트")
    try:
        url = f"http://localhost:8000/api/braking/analysis/{lap_id}"
        response = requests.get(url, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ 브레이킹 분석 API 성공!")
            braking = data.get('braking_analysis', {})
            summary = braking.get('summary', {})
            print(f"  - 총 브레이킹 존: {summary.get('total_brake_zones', 0)}")
            print(f"  - 평균 브레이킹 강도: {summary.get('average_brake_peak', 0)}")
        else:
            print(f"❌ 브레이킹 분석 API 실패: {response.text}")
    except Exception as e:
        print(f"❌ 브레이킹 분석 API 오류: {e}")
    
    # 2. 대시보드 개요 API 테스트
    print("\n" + "="*50)
    print("2. 대시보드 개요 API 테스트")
    try:
        url = f"http://localhost:8000/api/dashboard/overview/{real_user_id}"
        response = requests.get(url, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✅ 대시보드 개요 API 성공!")
            print(f"  - 총 랩 수: {data.get('total_laps', 0)}")
            summary = data.get('summary', {})
            print(f"  - 최고 랩 타임: {summary.get('best_lap_time', 'N/A')}")
        else:
            print(f"❌ 대시보드 개요 API 실패: {response.text}")
    except Exception as e:
        print(f"❌ 대시보드 개요 API 오류: {e}")

if __name__ == "__main__":
    test_with_real_user()

