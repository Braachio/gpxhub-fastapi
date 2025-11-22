#!/usr/bin/env python3
"""
실제 사용자 ID 확인
"""

from utils.supabase_client import supabase

def check_user_ids():
    # 실제 사용자 ID 확인
    result = supabase.table('lap_meta').select('user_id').limit(5).execute()
    if result.data:
        print('실제 사용자 ID들:')
        for row in result.data:
            user_id = row['user_id']
            print(f'  - {user_id}')
        
        # 첫 번째 사용자 ID로 테스트
        first_user_id = result.data[0]['user_id']
        print(f'\n첫 번째 사용자 ID로 테스트: {first_user_id}')
        return first_user_id
    else:
        print('사용자 데이터가 없습니다.')
        return None

if __name__ == "__main__":
    check_user_ids()

