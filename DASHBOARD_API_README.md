# 🏁 GPX 대시보드 API 문서

## 📋 개요

GPX 레이싱 데이터 분석 서비스의 실시간 대시보드와 브레이킹 분석 API입니다. 사용자들이 자신의 주행 성능을 분석하고 개선할 수 있는 종합적인 데이터를 제공합니다.

## 🚀 주요 기능

### 1. 실시간 대시보드
- **사용자 개요**: 최근 랩 요약, 성능 트렌드, 핵심 지표
- **랩 상세 분석**: 특정 랩의 종합적인 성능 분석
- **성능 트렌드**: 시간별 성능 변화 추이

### 2. 브레이킹 분석 대시보드
- **브레이킹 성능 분석**: 코너별 브레이킹 효율성 분석
- **비교 분석**: 다른 사용자들과의 성능 비교
- **리더보드**: 트랙별 최고 브레이킹 성능 순위
- **개선 제안**: AI 기반 브레이킹 개선 추천

## 📡 API 엔드포인트

### 대시보드 API

#### 1. 사용자 대시보드 개요
```http
GET /api/dashboard/overview/{user_id}
```

**파라미터:**
- `user_id` (path): 사용자 ID
- `track` (query, optional): 특정 트랙 필터링
- `days` (query, default: 30): 조회 기간 (일)

**응답 예시:**
```json
{
  "user_id": "user-123",
  "track": "seoul-circuit",
  "period_days": 30,
  "total_laps": 15,
  "summary": {
    "best_lap_time": 95.234,
    "average_lap_time": 97.456,
    "improvement_trend": 1.2,
    "total_distance": 1500.0
  },
  "recent_laps": [
    {
      "lap_id": "lap-456",
      "track": "seoul-circuit",
      "car": "BMW M3",
      "lap_time": 95.234,
      "created_at": "2024-01-15T10:30:00Z",
      "sector_count": 8,
      "sectors": [...]
    }
  ],
  "performance_metrics": {
    "consistency_score": 85.2,
    "improvement_rate": 3.1,
    "best_sector_times": [...]
  },
  "track_leaderboard": [...]
}
```

#### 2. 랩 상세 대시보드
```http
GET /api/dashboard/lap-detail/{lap_id}
```

**응답 예시:**
```json
{
  "lap_id": "lap-456",
  "meta": {
    "track": "seoul-circuit",
    "car": "BMW M3",
    "lap_time": 95.234
  },
  "performance_metrics": {
    "total_time": 95.234,
    "average_speed": 145.6,
    "max_speed": 180.2,
    "brake_efficiency": 25.3,
    "sector_count": 8
  },
  "sector_analysis": [...],
  "braking_analysis": {
    "segments": [...],
    "summary": {...}
  },
  "visualization_data": {
    "graph_data": [...],
    "brake_segments": [...],
    "sector_markers": [...]
  },
  "insights": [
    "브레이킹 강도가 높습니다. 더 부드러운 제동을 시도해보세요.",
    "고속 구간에서 좋은 성능을 보였습니다."
  ]
}
```

#### 3. 성능 트렌드 분석
```http
GET /api/dashboard/performance-trends/{user_id}
```

**파라미터:**
- `user_id` (path): 사용자 ID
- `track` (query, optional): 특정 트랙 필터링
- `days` (query, default: 30): 조회 기간 (일)

### 브레이킹 분석 API

#### 1. 브레이킹 분석 대시보드
```http
GET /api/braking/analysis/{lap_id}
```

**응답 예시:**
```json
{
  "lap_id": "lap-456",
  "track": "seoul-circuit",
  "braking_analysis": {
    "summary": {
      "total_brake_zones": 8,
      "average_brake_peak": 75.2,
      "average_deceleration": 12.5,
      "trail_braking_usage": 0.45,
      "abs_usage": 0.15
    },
    "visualization": {
      "brake_zones": [
        {
          "id": "brake_zone_0",
          "corner_index": 0,
          "segment_name": "코너 1",
          "start_time": 5.2,
          "end_time": 8.1,
          "brake_peak": 78.5,
          "decel_avg": 13.2,
          "trail_braking_ratio": 0.52,
          "abs_on_ratio": 0.12
        }
      ],
      "performance_metrics": [
        {
          "corner_index": 0,
          "brake_efficiency": 85.3,
          "smoothness_score": 78.9,
          "aggressiveness_score": 72.1
        }
      ],
      "corner_analysis": [
        {
          "corner_index": 0,
          "segment_name": "코너 1",
          "strengths": ["트레일 브레이킹 활용", "부드러운 브레이킹"],
          "weaknesses": [],
          "improvement_areas": ["현재 패턴 유지"]
        }
      ]
    },
    "feedbacks": [
      "코너 1: 브레이킹 타이밍이 빠른 랩들과 유사합니다."
    ],
    "overall_score": 82.1
  },
  "comparison": {
    "benchmark_data": [...],
    "comparison_metrics": {...}
  },
  "insights": [
    {
      "type": "success",
      "title": "트레일 브레이킹 활용",
      "message": "트레일 브레이킹을 잘 활용하고 있습니다!",
      "priority": "low"
    }
  ]
}
```

#### 2. 브레이킹 비교 분석
```http
GET /api/braking/comparison/{user_id}
```

**파라미터:**
- `user_id` (path): 사용자 ID
- `track` (query, optional): 특정 트랙 필터링
- `days` (query, default: 30): 조회 기간 (일)

#### 3. 브레이킹 리더보드
```http
GET /api/braking/leaderboard/{track}
```

**파라미터:**
- `track` (path): 트랙 이름
- `corner_index` (query, optional): 특정 코너 인덱스

## 🔧 사용 예시

### Python 클라이언트 예시

```python
import requests

# 대시보드 개요 조회
response = requests.get("http://localhost:8000/api/dashboard/overview/user-123")
dashboard_data = response.json()

# 브레이킹 분석 조회
response = requests.get("http://localhost:8000/api/braking/analysis/lap-456")
braking_data = response.json()

# 성능 트렌드 조회
response = requests.get("http://localhost:8000/api/dashboard/performance-trends/user-123?days=7")
trends_data = response.json()
```

### JavaScript 클라이언트 예시

```javascript
// 대시보드 개요 조회
const dashboardResponse = await fetch('/api/dashboard/overview/user-123');
const dashboardData = await dashboardResponse.json();

// 브레이킹 분석 조회
const brakingResponse = await fetch('/api/braking/analysis/lap-456');
const brakingData = await brakingResponse.json();
```

## 📊 데이터 구조

### 핵심 지표

#### 성능 지표
- **랩 타임**: 전체 랩 완주 시간
- **평균 속도**: 랩 전체 평균 속도
- **최고 속도**: 랩 중 최고 속도
- **브레이킹 효율성**: 브레이킹 시간 대비 전체 랩 시간 비율

#### 브레이킹 지표
- **브레이킹 강도**: 최대 브레이킹 압력 (%)
- **감속률**: 평균 감속 가속도 (m/s²)
- **트레일 브레이킹 비율**: 코너 진입 중 브레이킹 유지 비율
- **ABS 사용률**: ABS 작동 시간 비율
- **슬립 비율**: 타이어 슬립 발생 비율

#### 일관성 지표
- **일관성 점수**: 랩 타임 편차 기반 점수 (0-100)
- **개선율**: 최근 vs 초기 성능 비교
- **안정성 점수**: 브레이킹 패턴 일관성

### 시각화 데이터

#### 그래프 데이터
- **시간 시리즈**: 시간별 속도, 브레이크, 스로틀, 조향각
- **거리 시리즈**: 거리별 성능 지표
- **브레이킹 존**: 브레이킹 구간 마킹
- **섹터 마커**: 코너/섹터 구간 표시

#### 비교 데이터
- **벤치마크**: 다른 사용자들과의 성능 비교
- **트렌드**: 시간별 성능 변화
- **리더보드**: 최고 성능 순위

## 🎯 사용 시나리오

### 1. 드라이버 개선
- 자신의 브레이킹 패턴 분석
- 다른 드라이버들과의 성능 비교
- 구체적인 개선 제안 수신

### 2. 코치/멘토링
- 드라이버별 성능 트렌드 모니터링
- 약점 식별 및 개선 방향 제시
- 팀 내 성능 비교 분석

### 3. 데이터 분석
- 트랙별 최적 브레이킹 패턴 분석
- 차량별 성능 특성 파악
- 환경 조건별 성능 영향 분석

## 🚨 오류 처리

### 일반적인 오류 코드
- `400`: 잘못된 요청 파라미터
- `404`: 요청한 리소스를 찾을 수 없음
- `500`: 서버 내부 오류

### 오류 응답 예시
```json
{
  "detail": "랩 데이터를 찾을 수 없습니다."
}
```

## 🔄 업데이트 및 버전 관리

### 현재 버전: v1.0.0
- 실시간 대시보드 API
- 브레이킹 분석 대시보드 API
- 성능 트렌드 분석 API
- 리더보드 API

### 향후 계획
- AI 기반 개선 추천 강화
- 실시간 알림 시스템
- 모바일 최적화
- 고급 시각화 기능

## 🧪 테스트

테스트 스크립트를 사용하여 API를 테스트할 수 있습니다:

```bash
# 전체 테스트 실행
python test_dashboard_api.py

# 개별 테스트 실행
python test_dashboard_api.py overview
python test_dashboard_api.py braking lap-456
python test_dashboard_api.py leaderboard seoul-circuit
```

## 📞 지원

API 사용 중 문제가 발생하면 다음을 확인해주세요:
1. 서버가 실행 중인지 확인
2. 요청 파라미터가 올바른지 확인
3. 데이터베이스 연결 상태 확인

---

**GPX API v1.0.0** - 레이싱 데이터 분석의 새로운 차원
