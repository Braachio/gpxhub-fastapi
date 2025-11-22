#!/usr/bin/env python3
"""
직접 API 테스트 스크립트
"""

import requests
import json

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
            print(f"📊 응답 데이터 키들: {list(data.keys())}")
            
            if 'braking_analysis' in data:
                braking = data['braking_analysis']
                print(f"📊 브레이킹 분석 요약: {braking.get('summary', {})}")
                print(f"📊 브레이킹 존 수: {len(braking.get('visualization', {}).get('brake_zones', []))}")
            
            if 'insights' in data:
                print(f"📊 인사이트 수: {len(data['insights'])}")
                
        else:
            print(f"❌ API 호출 실패: {response.status_code}")
            print(f"❌ 응답 내용: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

def test_dashboard_api():
    user_id = 'test-user'
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
            
    except requests.exceptions.ConnectionError:
        print("❌ 서버에 연결할 수 없습니다. 서버가 실행 중인지 확인해주세요.")
    except Exception as e:
        print(f"❌ 오류 발생: {e}")

if __name__ == "__main__":
    print("🚀 API 테스트 시작\n")
    
    print("=" * 50)
    test_braking_api()
    
    print("\n" + "=" * 50)
    test_dashboard_api()
    
    print("\n🎉 테스트 완료")

