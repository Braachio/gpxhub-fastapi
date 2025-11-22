# iRacing SDK 문제 해결 가이드

## 문제: pyirsdk import 실패

### 증상
```
ModuleNotFoundError: No module named 'pyirsdk'
```
또는
```
⚠️ pyirsdk가 설치되지 않았습니다.
```

### 해결 방법

#### 방법 1: 올바른 Python 환경에서 설치

```powershell
# 현재 사용 중인 Python 확인
python --version
where python

# 해당 Python에 직접 설치
python -m pip install pyirsdk
```

#### 방법 2: pywin32 사용 (직접 메모리 접근)

`pyirsdk`가 작동하지 않으면, 직접 공유 메모리 접근 방식을 사용할 수 있습니다:

```powershell
pip install pywin32
```

그러면 스크립트가 자동으로 직접 메모리 접근 방식을 사용합니다.

#### 방법 3: 가상환경 사용

```powershell
# 가상환경 생성
cd ghostx_fastapi
python -m venv venv

# 가상환경 활성화
.\venv\Scripts\Activate.ps1

# 패키지 설치
pip install pyirsdk requests pywin32
```

### 현재 상태 확인

스크립트를 실행하면 어떤 방식이 사용 가능한지 표시됩니다:

```
✅ pyirsdk 로드 성공
```
또는
```
✅ 직접 공유 메모리 접근 방식 사용 가능
```

### 실제 사용 가능한 라이브러리 확인

다음 명령으로 사용 가능한 패키지를 확인하세요:

```powershell
python -c "import sys; print(sys.executable)"
pip list | findstr irsdk
pip list | findstr pywin32
```

### 대안: 수동 업로드 방식

SDK가 작동하지 않는 경우, iRacing에서 텔레메트리 파일을 수동으로 내보내서 웹 UI에서 업로드할 수 있습니다:

1. iRacing에서 세션 완료 후 텔레메트리 내보내기
2. `/iracing` 페이지 → "주행 데이터 분석" 탭
3. CSV/JSON 파일 업로드

