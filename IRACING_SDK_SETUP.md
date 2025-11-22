# iRacing SDK 설정 가이드

## Python 방법 (추천) ✅

### 장점
- ✅ 이미 FastAPI 백엔드가 있음
- ✅ pandas, numpy 등 데이터 분석 도구 사용 가능
- ✅ 공식 문서에 Python 예제가 많음
- ✅ 안정적인 라이브러리 존재

### 설치 방법

#### 옵션 1: pyirsdk 사용 (간단)

```bash
cd ghostx_fastapi
pip install pyirsdk
```

#### 옵션 2: 직접 공유 메모리 접근 (더 세밀한 제어)

Windows에서만 작동하며, `mmap` 모듈을 사용합니다.

```python
import mmap
import struct

# 공유 메모리 파일 경로
SHARED_MEMORY = 'Local\\IRSDKMemMapFileName'
```

### 사용 방법

#### 1. 로컬 서비스로 실행 (백그라운드)

**중요**: `ghostx_fastapi` 디렉토리에서 실행해야 합니다!

```bash
# PowerShell에서
cd ghostx_fastapi
python services\iracing_sdk_collector.py

# 또는 절대 경로로
python C:\Users\josan\ghostx\ghostx_fastapi\services\iracing_sdk_collector.py
```

환경 변수 설정:
```bash
# Windows PowerShell
$env:API_URL="http://localhost:3000"
$env:USER_TOKEN="your_supabase_token"

# 또는 .env 파일에 추가
API_URL=http://localhost:3000
USER_TOKEN=your_token
```

#### 2. FastAPI 엔드포인트로 제어

```bash
# 수집 시작
curl -X POST http://localhost:8000/api/iracing-sdk/start

# 상태 확인
curl http://localhost:8000/api/iracing-sdk/status

# 수집 중지
curl -X POST http://localhost:8000/api/iracing-sdk/stop
```

#### 3. 웹 UI에서 제어 (추후 구현)

Next.js에서 FastAPI 엔드포인트를 호출하여 수집 시작/중지

### 자동 시작 설정 (Windows)

#### 방법 1: 작업 스케줄러

1. Windows 작업 스케줄러 열기
2. "기본 작업 만들기"
3. 트리거: "iRacing.exe 실행 시"
4. 작업: Python 스크립트 실행

#### 방법 2: 배치 파일

`start-iracing-collector.bat`:
```batch
@echo off
cd /d C:\path\to\ghostx_fastapi
python services/iracing_sdk_collector.py
pause
```

iRacing 실행 시 이 배치 파일도 함께 실행

### 데이터 흐름

```
[iRacing Simulator]
    ↓ (공유 메모리)
[Python SDK Collector]
    ↓ (HTTP POST)
[Next.js API] (/api/iracing/telemetry/upload)
    ↓
[Supabase Database]
```

### 주의사항

1. **Windows에서만 작동**: iRacing SDK는 Windows 공유 메모리 방식
2. **iRacing 실행 필요**: 시뮬레이터가 실행 중이어야 데이터 수집 가능
3. **인증 토큰**: Supabase 인증 토큰이 필요 (선택사항, 로그인 후 토큰 사용)

### 문제 해결

#### "pyirsdk가 설치되지 않았습니다"
```bash
pip install pyirsdk
```

#### "iRacing이 실행되지 않았습니다"
- iRacing 시뮬레이터를 실행한 후 다시 시도

#### "SDK 연결 실패"
- Windows에서만 작동
- iRacing이 최신 버전인지 확인
- 관리자 권한으로 실행 시도

### 다음 단계

1. ✅ Python SDK 수집 서비스 구현 완료
2. ⏳ pyirsdk 설치 및 테스트
3. ⏳ 웹 UI에서 수집 제어 기능 추가
4. ⏳ 자동 시작 설정

