from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse
import pandas as pd
import io
from datetime import datetime
from typing import Optional
import hashlib
import json

from utils.supabase_client import supabase

router = APIRouter()

def clamp_decimal53(value):
    """DECIMAL(5,3) 범위로 클리핑 (±99.999)"""
    if value is None or pd.isna(value):
        return None
    if value > 99.999:
        return 99.999
    if value < -99.999:
        return -99.999
    return float(value)

def clamp_decimal63(value):
    """DECIMAL(6,3) 범위로 클리핑 (±999.999)"""
    if value is None or pd.isna(value):
        return None
    if value > 999.999:
        return 999.999
    if value < -999.999:
        return -999.999
    return float(value)

def clamp_01(value):
    """0.0~1.0 범위로 클리핑"""
    if value is None or pd.isna(value):
        return None
    if value > 1.0:
        return 1.0
    if value < 0.0:
        return 0.0
    return float(value)

@router.post("/iracing/telemetry/upload-csv")
async def upload_telemetry_csv(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    session_name: Optional[str] = Form(None),
    track_name: Optional[str] = Form(None),
    car_name: Optional[str] = Form(None),
):
    """
    CSV 파일을 업로드하여 텔레메트리 데이터를 Supabase에 저장
    
    FastAPI에서 처리하여 프론트엔드 렉 방지
    """
    try:
        # 1. CSV 파일 읽기
        content = await file.read()
        text = content.decode("utf-8", errors="ignore")
        lines = text.splitlines()
        
        if not lines:
            raise HTTPException(status_code=400, detail="CSV 파일이 비어있습니다")
        
        # 2. 헤더 찾기 (Time 필드가 있는 행)
        header_line_index = -1
        time_variations = ['time', 'elapsed_time', 'timestamp', 'elapsed', 'sessiontime', 'session time']
        
        for i, line in enumerate(lines[:100]):  # 처음 100줄만 확인
            if not line.strip():
                continue
            
            # 쉼표로 분리
            parts = [p.strip().strip('"\'') for p in line.split(',')]
            cleaned_parts = [p.lower().split('(')[0].strip() for p in parts]  # 단위 제거
            
            has_time = any(variation in cleaned_parts for variation in time_variations)
            if has_time and len(parts) > 3:
                header_line_index = i
                break
        
        if header_line_index == -1:
            # 대안: 많은 필드를 가진 첫 번째 비숫자 행
            for i, line in enumerate(lines[:100]):
                if not line.strip():
                    continue
                parts = [p.strip().strip('"\'') for p in line.split(',')]
                first_field = parts[0] if parts else ""
                try:
                    float(first_field)
                    continue  # 숫자로 시작하면 데이터 행
                except:
                    if len(parts) > 10:
                        header_line_index = i
                        break
        
        if header_line_index == -1:
            raise HTTPException(status_code=400, detail="CSV 헤더를 찾을 수 없습니다")
        
        # 3. pandas로 CSV 파싱 (헤더 행부터)
        header_line = lines[header_line_index]
        data_start = header_line_index + 1
        
        # 단위 행 체크
        if data_start < len(lines):
            next_line = lines[data_start].strip()
            if next_line:
                next_parts = [p.strip().strip('"\'') for p in next_line.split(',')]
                # 단위 행인지 체크 (모두 짧은 텍스트이고 숫자가 아님)
                is_unit_row = all(
                    len(p) < 10 and not p.replace('.', '').replace('-', '').isdigit()
                    for p in next_parts
                )
                if is_unit_row and len(next_parts) == len(header_line.split(',')):
                    data_start += 1
        
        # 데이터 부분만 읽기
        data_lines = [header_line] + lines[data_start:]
        csv_text = '\n'.join(data_lines)
        
        # pandas로 파싱
        try:
            df = pd.read_csv(io.StringIO(csv_text), skipinitialspace=True)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"CSV 파싱 실패: {str(e)}")
        
        if df.empty:
            raise HTTPException(status_code=400, detail="파싱된 데이터가 없습니다")
        
        # 4. 필드명 정규화 및 매핑
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        
        # 필드 매핑
        field_mapping = {
            'elapsed_time': ['time', 'elapsed_time', 'timestamp', 'elapsed', 'sessiontime', 'session_time'],
            'position_x': ['position_x', 'x', 'pos_x', 'gps_x', 'velocityx', 'velocity_x'],
            'position_y': ['position_y', 'y', 'pos_y', 'gps_y', 'velocityy', 'velocity_y'],
            'speed_kmh': ['speed_kmh', 'speed', 'velocity', 'kmh', 'ground_speed', 'groundspeed'],
            'throttle_position': ['throttle_position', 'throttle', 'thr', 'throttle_pos', 'throttlepos', 'throttleraw'],
            'brake_position': ['brake_position', 'brake', 'brk', 'brake_pedal_pos', 'brakepedalpos', 'brakeraw'],
            'steering_angle': ['steering_angle', 'steering', 'steer', 'wheel', 'steering_wheel_angle', 'steeringwheelangle'],
            'tire_temp_fl': ['tire_temp_fl', 'tire_fl', 'tire_temp_front_left', 'tyre_temp_fl_centre', 'lftempcl'],
            'tire_temp_fr': ['tire_temp_fr', 'tire_fr', 'tire_temp_front_right', 'tyre_temp_fr_centre', 'rftempcl'],
            'tire_temp_rl': ['tire_temp_rl', 'tire_rl', 'tire_temp_rear_left', 'tyre_temp_rl_centre', 'lrtempcl'],
            'tire_temp_rr': ['tire_temp_rr', 'tire_rr', 'tire_temp_rear_right', 'tyre_temp_rr_centre', 'rrtempcl'],
            'g_force_lateral': ['g_force_lateral', 'g_lat', 'lateral_g', 'g_lateral', 'g_force_lat', 'lataccel'],
            'g_force_longitudinal': ['g_force_longitudinal', 'g_long', 'longitudinal_g', 'g_longitudinal', 'g_force_long', 'longaccel'],
            'rpm': ['rpm', 'engine_rpm', 'engine_rpm', 'enginerpm'],
            'gear': ['gear', 'gear_number', 'gear_number'],
            'heading': ['heading', 'yaw', 'direction', 'yawnorth'],
        }
        
        # 표준 필드명으로 변환
        df_renamed = pd.DataFrame()
        for std_field, variations in field_mapping.items():
            for col in df.columns:
                col_clean = col.replace(' ', '_').replace('(', '').replace(')', '').lower()
                if col_clean in variations or any(v in col_clean for v in variations):
                    df_renamed[std_field] = df[col]
                    break
        
        # elapsed_time은 필수
        if 'elapsed_time' not in df_renamed.columns:
            # 원본 컬럼에서 time 찾기
            for col in df.columns:
                if 'time' in col.lower():
                    df_renamed['elapsed_time'] = df[col]
                    break
        
        if 'elapsed_time' not in df_renamed.columns:
            raise HTTPException(status_code=400, detail="시간 필드(elapsed_time, time 등)를 찾을 수 없습니다")
        
        # 5. 세션 생성
        max_time = df_renamed['elapsed_time'].max()
        min_time = df_renamed['elapsed_time'].min()
        duration_seconds = max_time - min_time
        
        session_start_time = datetime.now()
        session_end_time = datetime.now()
        
        # 데이터 해시 생성 (중복 검사)
        sample_hash_data = df_renamed.head(100).to_dict(orient='records')
        data_hash = hashlib.sha256(
            json.dumps({
                'user_id': user_id,
                'track_name': track_name,
                'car_name': car_name,
                'samples': sample_hash_data,
            }, sort_keys=True, default=str).encode()
        ).hexdigest()
        
        # 중복 검사
        existing = supabase.table('iracing_telemetry_sessions')\
            .select('id')\
            .eq('data_hash', data_hash)\
            .eq('user_id', user_id)\
            .execute()
        
        if existing.data:
            return {
                'session_id': existing.data[0]['id'],
                'samples_inserted': 0,
                'message': 'Duplicate session data',
                'duplicate': True
            }
        
        # 세션 삽입
        session_data = {
            'user_id': user_id,
            'session_name': session_name or f'CSV Upload: {file.filename}',
            'track_name': track_name or 'CSV Upload',
            'car_name': car_name or 'CSV Upload',
            'session_type': 'practice',
            'start_time': session_start_time.isoformat(),
            'end_time': session_end_time.isoformat(),
            'duration_seconds': float(duration_seconds),
            'sample_count': len(df_renamed),
            'sample_rate_hz': float(len(df_renamed) / duration_seconds) if duration_seconds > 0 else None,
            'data_hash': data_hash,
            'is_complete': True,
            'notes': {
                'source': 'csv_upload_fastapi',
                'filename': file.filename,
            }
        }
        
        session_result = supabase.table('iracing_telemetry_sessions')\
            .insert(session_data)\
            .execute()
        
        if not session_result.data:
            raise HTTPException(status_code=500, detail="세션 생성 실패")
        
        session_id = session_result.data[0]['id']
        
        # 6. 샘플 데이터 분리 및 배치 삽입 (lap_controls/lap_vehicle_status 패턴)
        controls_samples = []
        vehicle_samples = []
        advanced_samples = []
        
        for _, row in df_renamed.iterrows():
            elapsed_time = float(row.get('elapsed_time', 0))
            
            # 제어 입력 데이터
            controls = {
                'session_id': session_id,
                'elapsed_time': elapsed_time,
                'throttle_position': clamp_01(row.get('throttle_position')),
                'brake_position': clamp_01(row.get('brake_position')),
                'steering_angle': float(row.get('steering_angle')) if pd.notna(row.get('steering_angle')) else None,
                'clutch_position': clamp_01(row.get('clutch_position')),
            }
            controls_samples.append(controls)
            
            # 차량 상태 및 위치 데이터
            vehicle = {
                'session_id': session_id,
                'elapsed_time': elapsed_time,
                'speed_ms': float(row.get('speed_ms')) if pd.notna(row.get('speed_ms')) else None,
                'speed_kmh': float(row.get('speed_kmh')) if pd.notna(row.get('speed_kmh')) else None,
                'rpm': int(row.get('rpm')) if pd.notna(row.get('rpm')) else None,
                'gear': int(row.get('gear')) if pd.notna(row.get('gear')) else None,
                'engine_power': float(row.get('engine_power')) if pd.notna(row.get('engine_power')) else None,
                'engine_torque': float(row.get('engine_torque')) if pd.notna(row.get('engine_torque')) else None,
                'position_x': float(row.get('position_x')) if pd.notna(row.get('position_x')) else None,
                'position_y': float(row.get('position_y')) if pd.notna(row.get('position_y')) else None,
                'position_z': float(row.get('position_z')) if pd.notna(row.get('position_z')) else None,
                'latitude': float(row.get('latitude')) if pd.notna(row.get('latitude')) else None,
                'longitude': float(row.get('longitude')) if pd.notna(row.get('longitude')) else None,
                'heading': float(row.get('heading')) if pd.notna(row.get('heading')) else None,
                'distance_lap': float(row.get('distance_lap')) if pd.notna(row.get('distance_lap')) else None,
            }
            vehicle_samples.append(vehicle)
            
            # 고급 동역학 데이터
            advanced = {
                'session_id': session_id,
                'elapsed_time': elapsed_time,
                'tire_temp_fl': float(row.get('tire_temp_fl')) if pd.notna(row.get('tire_temp_fl')) else None,
                'tire_temp_fr': float(row.get('tire_temp_fr')) if pd.notna(row.get('tire_temp_fr')) else None,
                'tire_temp_rl': float(row.get('tire_temp_rl')) if pd.notna(row.get('tire_temp_rl')) else None,
                'tire_temp_rr': float(row.get('tire_temp_rr')) if pd.notna(row.get('tire_temp_rr')) else None,
                'tire_pressure_fl': clamp_decimal63(row.get('tire_pressure_fl')),
                'tire_pressure_fr': clamp_decimal63(row.get('tire_pressure_fr')),
                'tire_pressure_rl': clamp_decimal63(row.get('tire_pressure_rl')),
                'tire_pressure_rr': clamp_decimal63(row.get('tire_pressure_rr')),
                'tire_wear_fl': clamp_01(row.get('tire_wear_fl')),
                'tire_wear_fr': clamp_01(row.get('tire_wear_fr')),
                'tire_wear_rl': clamp_01(row.get('tire_wear_rl')),
                'tire_wear_rr': clamp_01(row.get('tire_wear_rr')),
                'suspension_travel_fl': float(row.get('suspension_travel_fl')) if pd.notna(row.get('suspension_travel_fl')) else None,
                'suspension_travel_fr': float(row.get('suspension_travel_fr')) if pd.notna(row.get('suspension_travel_fr')) else None,
                'suspension_travel_rl': float(row.get('suspension_travel_rl')) if pd.notna(row.get('suspension_travel_rl')) else None,
                'suspension_travel_rr': float(row.get('suspension_travel_rr')) if pd.notna(row.get('suspension_travel_rr')) else None,
                'ride_height_fl': float(row.get('ride_height_fl')) if pd.notna(row.get('ride_height_fl')) else None,
                'ride_height_fr': float(row.get('ride_height_fr')) if pd.notna(row.get('ride_height_fr')) else None,
                'ride_height_rl': float(row.get('ride_height_rl')) if pd.notna(row.get('ride_height_rl')) else None,
                'ride_height_rr': float(row.get('ride_height_rr')) if pd.notna(row.get('ride_height_rr')) else None,
                'g_force_lateral': clamp_decimal53(row.get('g_force_lateral')),
                'g_force_longitudinal': clamp_decimal53(row.get('g_force_longitudinal')),
                'g_force_vertical': clamp_decimal53(row.get('g_force_vertical')),
                'wheel_slip_fl': clamp_decimal53(row.get('wheel_slip_fl')),
                'wheel_slip_fr': clamp_decimal53(row.get('wheel_slip_fr')),
                'wheel_slip_rl': clamp_decimal53(row.get('wheel_slip_rl')),
                'wheel_slip_rr': clamp_decimal53(row.get('wheel_slip_rr')),
                'brake_temperature_fl': float(row.get('brake_temperature_fl')) if pd.notna(row.get('brake_temperature_fl')) else None,
                'brake_temperature_fr': float(row.get('brake_temperature_fr')) if pd.notna(row.get('brake_temperature_fr')) else None,
                'brake_temperature_rl': float(row.get('brake_temperature_rl')) if pd.notna(row.get('brake_temperature_rl')) else None,
                'brake_temperature_rr': float(row.get('brake_temperature_rr')) if pd.notna(row.get('brake_temperature_rr')) else None,
                'abs_active': bool(row.get('abs_active')) if pd.notna(row.get('abs_active')) else None,
                'traction_control_active': bool(row.get('traction_control_active')) if pd.notna(row.get('traction_control_active')) else None,
                'lap_number': int(row.get('lap_number')) if pd.notna(row.get('lap_number')) else None,
                'sector_number': int(row.get('sector_number')) if pd.notna(row.get('sector_number')) else None,
                'fuel_level': float(row.get('fuel_level')) if pd.notna(row.get('fuel_level')) else None,
                'fuel_pressure': float(row.get('fuel_pressure')) if pd.notna(row.get('fuel_pressure')) else None,
            }
            advanced_samples.append(advanced)
        
        # 배치 삽입 (500개씩) - 각 테이블별로
        batch_size = 500
        total_inserted_controls = 0
        total_inserted_vehicle = 0
        total_inserted_advanced = 0
        
        def insert_batch(table_name, samples_list):
            total = 0
            for i in range(0, len(samples_list), batch_size):
                batch = samples_list[i:i + batch_size]
                try:
                    result = supabase.table(table_name).insert(batch).execute()
                    if result.data:
                        total += len(batch)
                    else:
                        # 실패 시 더 작은 단위로 재시도
                        for j in range(0, len(batch), 100):
                            small_batch = batch[j:j + 100]
                            retry_result = supabase.table(table_name).insert(small_batch).execute()
                            if retry_result.data:
                                total += len(small_batch)
                except Exception as e:
                    error_msg = str(e)
                    print(f"Error inserting {table_name} batch {i // batch_size}: {error_msg}")
                    # 테이블이 없는 경우 (relation does not exist) 예외 처리
                    if 'relation' in error_msg.lower() or 'does not exist' in error_msg.lower() or '42P01' in error_msg:
                        raise HTTPException(
                            status_code=500, 
                            detail=f"데이터베이스 테이블 '{table_name}'이 존재하지 않습니다. 마이그레이션을 먼저 실행해주세요: DATABASE_MIGRATION_IRACING_TELEMETRY_V2.sql"
                        )
                    # 재시도
                    for j in range(0, len(batch), 100):
                        small_batch = batch[j:j + 100]
                        try:
                            retry_result = supabase.table(table_name).insert(small_batch).execute()
                            if retry_result.data:
                                total += len(small_batch)
                        except:
                            pass
            return total
        
        # 새 테이블 구조로 시도 (분리된 테이블)
        try:
            total_inserted_controls = insert_batch('iracing_telemetry_controls', controls_samples)
            total_inserted_vehicle = insert_batch('iracing_telemetry_vehicle', vehicle_samples)
            total_inserted_advanced = insert_batch('iracing_telemetry_advanced', advanced_samples)
            
            total_inserted = max(total_inserted_controls, total_inserted_vehicle, total_inserted_advanced)
            
            return {
                'session_id': session_id,
                'samples_inserted': total_inserted,
                'samples_total': len(controls_samples),
                'controls_inserted': total_inserted_controls,
                'vehicle_inserted': total_inserted_vehicle,
                'advanced_inserted': total_inserted_advanced,
                'message': f'Successfully uploaded {total_inserted} samples (controls: {total_inserted_controls}, vehicle: {total_inserted_vehicle}, advanced: {total_inserted_advanced})'
            }
        except HTTPException:
            # 테이블이 없는 경우, 기존 단일 테이블로 fallback
            raise  # HTTPException은 그대로 전달
        except Exception as e:
            error_msg = str(e)
            print(f"⚠️ 새 테이블 구조 실패, 기존 테이블로 fallback 시도: {error_msg}")
            
            # 기존 단일 테이블로 fallback (iracing_telemetry_samples)
            # 모든 데이터를 하나의 테이블에 저장
            fallback_samples = []
            for i in range(len(controls_samples)):
                elapsed_time = controls_samples[i]['elapsed_time']
                controls = controls_samples[i]
                vehicle = vehicle_samples[i] if i < len(vehicle_samples) else {}
                advanced = advanced_samples[i] if i < len(advanced_samples) else {}
                
                combined = {
                    'session_id': session_id,
                    'elapsed_time': elapsed_time,
                    **{k: v for k, v in controls.items() if k != 'session_id' and k != 'id'},
                    **{k: v for k, v in vehicle.items() if k != 'session_id' and k != 'id'},
                    **{k: v for k, v in advanced.items() if k != 'session_id' and k != 'id'},
                }
                fallback_samples.append(combined)
            
            # 기존 테이블에 삽입
            fallback_inserted = 0
            for i in range(0, len(fallback_samples), batch_size):
                batch = fallback_samples[i:i + batch_size]
                try:
                    result = supabase.table('iracing_telemetry_samples').insert(batch).execute()
                    if result.data:
                        fallback_inserted += len(batch)
                except Exception as fallback_error:
                    print(f"Fallback insert 실패: {fallback_error}")
                    # 더 작은 단위로 재시도
                    for j in range(0, len(batch), 100):
                        small_batch = batch[j:j + 100]
                        try:
                            retry_result = supabase.table('iracing_telemetry_samples').insert(small_batch).execute()
                            if retry_result.data:
                                fallback_inserted += len(small_batch)
                        except:
                            pass
            
            return {
                'session_id': session_id,
                'samples_inserted': fallback_inserted,
                'samples_total': len(fallback_samples),
                'message': f'⚠️ 기존 테이블 구조로 업로드 완료: {fallback_inserted}개 (새 테이블 마이그레이션 필요)',
                'fallback': True
            }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"업로드 실패: {str(e)}")

