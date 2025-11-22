"""
iRacing SDK 텔레메트리 데이터 수집 서비스

사용법:
1. pip install pyirsdk (또는 직접 공유 메모리 접근)
2. python services/iracing_sdk_collector.py

환경 변수:
- API_URL: Next.js API URL (기본값: http://localhost:3000)
- USER_TOKEN: Supabase 인증 토큰 (선택사항)
"""

import time
import json
import requests
import threading
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

# Windows 콘솔 인코딩 설정 (한글/이모지 출력 방지)
import sys
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# iRacing SDK 접근을 위한 여러 방법 시도
IRSDK = None
IRSDK_AVAILABLE = False
DIRECT_MEMORY_ACCESS = False

# 방법 1: pyirsdk 시도
try:
    from pyirsdk import IRSDK
    IRSDK_AVAILABLE = True
    print("[OK] pyirsdk loaded successfully")
except ImportError as e:
    pass

# 방법 2: 직접 공유 메모리 접근 (Windows)
if not IRSDK_AVAILABLE:
    try:
        import mmap
        import struct
        import win32file
        import win32api
        DIRECT_MEMORY_ACCESS = True
        print("[OK] Direct memory access available")
    except ImportError:
        DIRECT_MEMORY_ACCESS = False
        print("[WARNING] Neither pyirsdk nor direct memory access available")
        print("Install: pip install pyirsdk or pywin32")


@dataclass
class TelemetrySample:
    """텔레메트리 샘플 데이터"""
    elapsed_time: float
    throttle_position: Optional[float] = None
    brake_position: Optional[float] = None
    steering_angle: Optional[float] = None
    speed_ms: Optional[float] = None
    speed_kmh: Optional[float] = None
    rpm: Optional[int] = None
    gear: Optional[int] = None
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    position_z: Optional[float] = None
    heading: Optional[float] = None
    distance_lap: Optional[float] = None
    tire_temp_fl: Optional[float] = None
    tire_temp_fr: Optional[float] = None
    tire_temp_rl: Optional[float] = None
    tire_temp_rr: Optional[float] = None
    g_force_lateral: Optional[float] = None
    g_force_longitudinal: Optional[float] = None
    lap_number: Optional[int] = None
    fuel_level: Optional[float] = None


class IRacingSDKCollector:
    """iRacing SDK 텔레메트리 데이터 수집기"""
    
    def __init__(self, api_url: str = "http://localhost:3000", user_token: Optional[str] = None):
        self.api_url = api_url
        self.user_token = user_token
        self.ir = None
        self.is_running = False
        self.session_id: Optional[str] = None
        self.session_start_time: Optional[datetime] = None
        self.samples: List[Dict[str, Any]] = []
        self.last_upload_time = time.time()
        self.collect_thread: Optional[threading.Thread] = None
        
        # 수집 설정
        self.collection_interval = 1.0 / 60.0  # 60Hz (초당 60회)
        self.batch_size = 60  # 1초치 데이터를 배치로 전송
        self.upload_interval = 10.0  # 10초마다 강제 업로드
        
    def connect(self) -> bool:
        """iRacing SDK에 연결"""
        if IRSDK_AVAILABLE and IRSDK:
            try:
                self.ir = IRSDK()
                self.ir.startup()
                
                if self.ir.is_connected():
                    print("[OK] iRacing SDK connected (pyirsdk)")
                    return True
                else:
                    print("[WARNING] iRacing is not running")
                    return False
            except Exception as e:
                print(f"[ERROR] SDK connection failed: {e}")
                return False
        elif DIRECT_MEMORY_ACCESS:
            try:
                # 직접 공유 메모리 접근 구현
                self.ir = self._connect_direct_memory()
                if self.ir:
                    print("[OK] iRacing SDK connected (direct memory access)")
                    return True
                else:
                    print("[WARNING] iRacing is not running")
                    return False
            except Exception as e:
                print(f"[ERROR] Direct memory access failed: {e}")
                return False
        else:
            print("[ERROR] No iRacing SDK access method available")
            print("Install: pip install pyirsdk or pywin32")
            return False
    
    def _connect_direct_memory(self):
        """직접 공유 메모리 접근 (Windows)"""
        try:
            # Windows 공유 메모리 파일 경로
            mem_file = win32file.OpenFileMapping(
                win32file.FILE_MAP_READ,
                False,
                "Local\\IRSDKMemMapFileName"
            )
            
            if mem_file:
                mem_view = win32api.MapViewOfFile(
                    mem_file,
                    win32file.FILE_MAP_READ,
                    0,
                    0,
                    0
                )
                return {
                    'handle': mem_file,
                    'view': mem_view,
                    'connected': True
                }
        except Exception as e:
            return None
        return None
    
    def disconnect(self):
        """iRacing SDK 연결 해제"""
        if self.ir:
            try:
                if IRSDK_AVAILABLE and hasattr(self.ir, 'shutdown'):
                    self.ir.shutdown()
                elif DIRECT_MEMORY_ACCESS and isinstance(self.ir, dict):
                    # 직접 메모리 접근 해제
                    if 'view' in self.ir:
                        win32api.UnmapViewOfFile(self.ir['view'])
                    if 'handle' in self.ir:
                        win32file.CloseHandle(self.ir['handle'])
                print("[OK] SDK disconnected")
            except Exception as e:
                print(f"[WARNING] Disconnect error: {e}")
            self.ir = None
    
    def read_sdk_data(self) -> Optional[Dict[str, Any]]:
        """SDK에서 데이터 읽기"""
        if not self.ir:
            return None
        
        # pyirsdk 방식
        if IRSDK_AVAILABLE and hasattr(self.ir, 'is_connected'):
            if not self.ir.is_connected():
                return None
            try:
                # pyirsdk를 사용한 데이터 읽기
                data = {
                    'connected': True,
                    'session_time': self.ir['SessionTime'] if 'SessionTime' in self.ir else 0,
                    'speed': self.ir['Speed'] if 'Speed' in self.ir else 0,  # mph
                    'rpm': int(self.ir['RPM']) if 'RPM' in self.ir else 0,
                    'throttle': self.ir['Throttle'] if 'Throttle' in self.ir else 0,  # 0-100
                    'brake': self.ir['Brake'] if 'Brake' in self.ir else 0,  # 0-100
                    'steering': self.ir['SteeringWheelAngle'] if 'SteeringWheelAngle' in self.ir else 0,  # 라디안
                    'gear': int(self.ir['Gear']) if 'Gear' in self.ir else 0,
                    'pos_x': self.ir['CarIdxLapDistPct'] if 'CarIdxLapDistPct' in self.ir else None,
                    'heading': self.ir['Heading'] if 'Heading' in self.ir else None,
                    'lap_dist': self.ir['LapDist'] if 'LapDist' in self.ir else None,
                    'lf_temp': self.ir['LFtempRL'] if 'LFtempRL' in self.ir else None,
                    'rf_temp': self.ir['RFtempRL'] if 'RFtempRL' in self.ir else None,
                    'lr_temp': self.ir['LRtempRL'] if 'LRtempRL' in self.ir else None,
                    'rr_temp': self.ir['RRtempRL'] if 'RRtempRL' in self.ir else None,
                    'lat_g': self.ir['LatAccel'] if 'LatAccel' in self.ir else None,
                    'long_g': self.ir['LongAccel'] if 'LongAccel' in self.ir else None,
                    'lap': int(self.ir['Lap']) if 'Lap' in self.ir else None,
                    'fuel_level': self.ir['FuelLevel'] if 'FuelLevel' in self.ir else None,
                }
                return data
            except Exception as e:
                print(f"[WARNING] Data read error: {e}")
                return None
        
        # 직접 메모리 접근 방식
        elif DIRECT_MEMORY_ACCESS and isinstance(self.ir, dict) and self.ir.get('connected'):
            # TODO: 직접 메모리에서 데이터 파싱 구현
            # 현재는 기본 구조만 반환
            return {
                'connected': True,
                'session_time': 0,
                'speed': 0,
                'rpm': 0,
                'throttle': 0,
                'brake': 0,
                'steering': 0,
                'gear': 0,
            }
        
        return None
    
    def convert_to_sample(self, sdk_data: Dict[str, Any], elapsed_time: float) -> Dict[str, Any]:
        """SDK 데이터를 TelemetrySample 형식으로 변환"""
        speed_ms = sdk_data.get('speed', 0) * 0.44704 if sdk_data.get('speed') else None  # mph → m/s
        speed_kmh = sdk_data.get('speed', 0) * 1.60934 if sdk_data.get('speed') else None  # mph → km/h
        
        return {
            'elapsed_time': elapsed_time,
            'throttle_position': sdk_data.get('throttle', 0) / 100.0 if sdk_data.get('throttle') is not None else None,
            'brake_position': sdk_data.get('brake', 0) / 100.0 if sdk_data.get('brake') is not None else None,
            'steering_angle': sdk_data.get('steering'),
            'speed_ms': speed_ms,
            'speed_kmh': speed_kmh,
            'rpm': sdk_data.get('rpm'),
            'gear': sdk_data.get('gear'),
            'position_x': sdk_data.get('pos_x'),
            'heading': sdk_data.get('heading'),
            'distance_lap': sdk_data.get('lap_dist'),
            'tire_temp_fl': sdk_data.get('lf_temp'),
            'tire_temp_fr': sdk_data.get('rf_temp'),
            'tire_temp_rl': sdk_data.get('lr_temp'),
            'tire_temp_rr': sdk_data.get('rr_temp'),
            'g_force_lateral': sdk_data.get('lat_g'),
            'g_force_longitudinal': sdk_data.get('long_g'),
            'lap_number': sdk_data.get('lap'),
            'fuel_level': sdk_data.get('fuel_level'),
        }
    
    def upload_samples(self, samples: List[Dict[str, Any]]):
        """서버로 샘플 데이터 전송"""
        if not samples:
            return
        
        try:
            # 세션 정보 가져오기 (SDK에서)
            sdk_data = self.read_sdk_data()
            if not sdk_data or not sdk_data.get('connected'):
                print("[WARNING] iRacing connection lost")
                return False
            
            upload_request = {
                'session': {
                    'user_id': 'current_user',  # 실제로는 토큰에서 추출
                    'session_name': f'iRacing Session {datetime.now().isoformat()}',
                    'start_time': self.session_start_time.isoformat() if self.session_start_time else datetime.now().isoformat(),
                    'end_time': datetime.now().isoformat(),
                },
                'samples': samples,
            }
            
            headers = {
                'Content-Type': 'application/json',
            }
            
            if self.user_token:
                headers['Authorization'] = f'Bearer {self.user_token}'
            
            response = requests.post(
                f'{self.api_url}/api/iracing/telemetry/upload',
                json=upload_request,
                headers=headers,
                timeout=10
            )
            
            if response.ok:
                data = response.json()
                print(f"[OK] {len(samples)} samples uploaded (Session ID: {data.get('session_id')})")
                return True
            else:
                error = response.json() if response.content else {}
                print(f"[ERROR] Upload failed: {error.get('error', 'Unknown error')}")
                return False
        except Exception as e:
            print(f"[ERROR] Upload error: {e}")
            return False
    
    def collect_loop(self):
        """수집 루프 (별도 스레드에서 실행)"""
        while self.is_running:
            try:
                sdk_data = self.read_sdk_data()
                
                if not sdk_data or not sdk_data.get('connected'):
                    print("[WARNING] iRacing connection lost, stopping collection")
                    self.stop()
                    break
                
                # 샘플 생성
                elapsed_time = (datetime.now() - self.session_start_time).total_seconds() if self.session_start_time else 0
                sample = self.convert_to_sample(sdk_data, elapsed_time)
                self.samples.append(sample)
                
                # 배치 크기에 도달하면 업로드
                if len(self.samples) >= self.batch_size:
                    batch = self.samples[:self.batch_size]
                    self.samples = self.samples[self.batch_size:]
                    self.upload_samples(batch)
                    self.last_upload_time = time.time()
                
                # 주기적 강제 업로드 (세션 종료 대비)
                if time.time() - self.last_upload_time > self.upload_interval and self.samples:
                    batch = self.samples.copy()
                    self.samples = []
                    self.upload_samples(batch)
                    self.last_upload_time = time.time()
                
                time.sleep(self.collection_interval)
                
            except Exception as e:
                print(f"[ERROR] Collection error: {e}")
                time.sleep(1.0)
    
    def start(self):
        """수집 시작"""
        if self.is_running:
            print("[WARNING] Already collecting")
            return False
        
        if not self.connect():
            return False
        
        print("[START] iRacing SDK telemetry collection started...")
        self.is_running = True
        self.session_start_time = datetime.now()
        self.samples = []
        
        # 별도 스레드에서 수집
        self.collect_thread = threading.Thread(target=self.collect_loop, daemon=True)
        self.collect_thread.start()
        
        return True
    
    def stop(self):
        """수집 중지"""
        if not self.is_running:
            return
        
        print("[STOP] Stopping collection...")
        self.is_running = False
        
        # 남은 샘플 업로드
        if self.samples:
            self.upload_samples(self.samples)
            self.samples = []
        
        self.disconnect()
        print("[OK] Collection completed")


def main():
    """CLI 실행"""
    import os
    import signal
    
    api_url = os.getenv('API_URL', 'http://localhost:3000')
    user_token = os.getenv('USER_TOKEN')
    
    collector = IRacingSDKCollector(api_url=api_url, user_token=user_token)
    
    # 종료 처리
    def signal_handler(sig, frame):
        print('\n종료 중...')
        collector.stop()
        exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 시작
    if collector.start():
        print("Collecting... (Press Ctrl+C to stop)")
        try:
            # 메인 스레드가 종료되지 않도록 대기
            while collector.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            collector.stop()
    else:
        print("[ERROR] Failed to start collection")


if __name__ == '__main__':
    main()

