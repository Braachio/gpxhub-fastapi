# iRacing SDK 수집 서비스 실행 가이드

## ⚠️ 중요: 디렉토리 위치

이 스크립트는 `ghostx_fastapi` 디렉토리에서 실행해야 합니다!

## 빠른 시작

### 1. 현재 위치 확인

```powershell
# 현재 디렉토리 확인
pwd

# 루트 디렉토리로 이동 (필요한 경우)
cd C:\Users\josan\ghostx
```

### 2. ghostx_fastapi로 이동

```powershell
cd ghostx_fastapi
```

### 3. 스크립트 실행

```powershell
python services\iracing_sdk_collector.py
```

## 전체 경로로 실행 (권장)

```powershell
python C:\Users\josan\ghostx\ghostx_fastapi\services\iracing_sdk_collector.py
```

## 환경 변수 설정 (선택사항)

```powershell
# Next.js API URL 설정
$env:API_URL="http://localhost:3000"

# Supabase 토큰 설정 (선택사항)
$env:USER_TOKEN="your_token_here"

# 실행
python services\iracing_sdk_collector.py
```

## 필수 패키지 설치

```powershell
cd ghostx_fastapi
pip install pyirsdk requests
```

## 문제 해결

### "can't open file" 오류
- ✅ `ghostx_fastapi` 디렉토리에서 실행해야 합니다
- ✅ 전체 경로를 사용하세요

### "pyirsdk가 설치되지 않았습니다"
```powershell
pip install pyirsdk
```

### "iRacing이 실행되지 않았습니다"
- iRacing 시뮬레이터를 먼저 실행하세요

