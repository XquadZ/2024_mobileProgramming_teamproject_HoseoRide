# HoseoRide / BusTracker 프로젝트 개요

이 저장소는 **호서대학교 셔틀버스**를 대상으로,

- 도로 위 **CCTV 영상(ITS / UTIC)** 에서 버스를 자동으로 감지하고  
- **학교 공식 시간표·노선 정보**와 조합하여 **현재 어느 노선의 버스가 어디쯤인지**를 추정한 뒤  
- 웹/앱 클라이언트에 **실시간 위치·시간표·노선 정보**를 제공하는

**엔드 투 엔드 버스 추적 시스템**입니다.

구성은 크게 두 부분으로 나뉩니다.

- `bus_server` : Python 기반 백엔드 (FastAPI, PostgreSQL, Redis, YOLO, CCTV 연동)
- `bus_client` : Flutter 기반 클라이언트 앱 (노선/시간표/실시간 위치 UI)

이 문서는 ** bustracker-main 전체 구조 + 코드 역할 + 실행 환경 **을 한 번에 파악할 수 있도록 정리한 README입니다.

---

## 1. 전체 구조

```text
bustracker-main/
├─ bus_server/          # 백엔드 API + 배치 스케줄러 + CCTV/YOLO 파이프라인
│  ├─ app/
│  │  ├─ api/           # REST / WebSocket 엔드포인트
│  │  ├─ core/          # DB, Redis 클라이언트
│  │  ├─ models/        # SQLAlchemy ORM 모델
│  │  ├─ services/      # 버스 감지, CCTV 스트림, 위치 추정 등 비즈니스 로직
│  │  ├─ config.py      # 환경변수 기반 설정 (DB/Redis/API 키 등)
│  │  └─ main.py        # FastAPI 앱 진입점
│  ├─ scripts/          # 초기 데이터 시드, 카메라 수집/매핑 유틸리티
│  ├─ tests/            # API/서비스 단위 테스트
│  ├─ docker-compose.yml
│  ├─ Dockerfile
│  ├─ requirements.txt
│  └─ .env.example
│
├─ bus_client/          # 셔틀 조회 Flutter 앱
│  ├─ lib/
│  │  ├─ core/          # 라우팅(go_router), 테마, 상수(API URL 등)
│  │  ├─ models/        # 노선/시간표/버스 위치 DTO
│  │  ├─ providers/     # Riverpod 상태 관리 (API, WebSocket)
│  │  ├─ screens/       # 홈, 노선 목록/상세, 시간표 화면
│  │  ├─ services/      # REST API, WebSocket 클라이언트
│  │  ├─ app.dart       # MaterialApp.router 설정
│  │  └─ main.dart      # Flutter 엔트리 포인트
│  └─ pubspec.yaml
│
└─ crawler/
   └─ README.md         # (현재 문서)
```

---

## 2. 백엔드 (`bus_server`) 상세

### 2.1 사용 기술

- **프레임워크**: FastAPI, Uvicorn
- **DB / ORM**: PostgreSQL + SQLAlchemy (Async, `asyncpg`)
- **캐시 / 실시간**: Redis (Pub/Sub, 위치 캐시)
- **컴퓨터 비전**: OpenCV, ONNX Runtime, YOLOv8 ONNX 모델
- **네트워크 / 기타**: httpx, shapely(지리 계산), easyocr(옵션, LED 판독용)
- **컨테이너/배포**: Docker, docker-compose

### 2.2 주요 개념 흐름

서버는 크게 다음 단계를 반복합니다.

1. **노선/시간표 정보 로딩**
   - `scripts/seed_data.py` 실행 시,  
     - 아산→천안 / 천안→아산 왕복 노선  
     - 요일별(평일/금요일/토요일/공휴일) 시간표  
     를 DB의 `shuttle_routes`, `schedules` 테이블에 저장합니다.

2. **CCTV 카메라 수집 및 노선 매핑**
   - `scripts/fetch_cameras.py` 실행 시,
     - ITS OpenAPI, UTIC HTML에서 아산~천안 구간 카메라를 수집
     - 노선 폴리라인에 가까운 카메라를 찾고,  
       `route_camera_mappings` 테이블에 **노선별 카메라 시퀀스 + 예상 도달 시간**을 기록합니다.

3. **스케줄러 실행 (실시간 감지 루프)**
   - `app/services/scheduler.py` 의 하이브리드 스케줄러가,
     - **SNAPSHOT 모드 카메라**: 주기적으로 한 프레임만 뽑아 YOLO로 버스 감지
     - **STREAM 모드 카메라**: 버스가 포착된 구간은 HLS 스트림을 잠시 집중 분석
   - 버스가 감지되면:
     - `route_matcher`로 **어느 노선/회차(trip)인지** 추론
     - `location_estimator`로 **노선 폴리라인 상에서 현재 위치 보간**
     - Redis에 `bus:location:{route_id}:{trip_id}` 키로 위치 정보 저장 +  
       `bus:updates:{route_id}` 채널로 Pub/Sub 발행

4. **API / WebSocket 제공**
   - REST:
     - `/api/routes` : 노선 목록 + 경로 폴리라인
     - `/api/routes/{id}` : 개별 노선 상세
     - `/api/routes/{id}/schedules` : 해당 노선 시간표
     - `/api/schedules?day_type=weekday|saturday|holiday` : 요일별 전체 시간표
     - `/api/buses/location` / `/api/buses/location/{route_id}` : 현재 버스 위치 리스트
   - WebSocket:
     - `/ws/location` : 모든 노선 위치 실시간 스트림
     - `/ws/location/{route_id}` : 특정 노선 위치 실시간 스트림

### 2.3 주요 코드 파일 별 역할

- `app/main.py`
  - FastAPI 앱 생성, DB 테이블 생성, 스케줄러(start/stop) 라이프사이클 관리
  - `app.include_router(...)`로 REST/WS 라우터 등록

- `app/config.py`
  - `.env` 기반 설정 클래스 (`Settings`)
  - DB URL, Redis URL, UTIC/ITS API KEY, YOLO 모델 경로, 기본 버스 속도 등

- `app/core/database.py` / `app/core/redis_client.py`
  - **PostgreSQL**: `AsyncEngine`, `async_session`, `get_db` 의존성
  - **Redis**: `redis_client` 전역 클라이언트, `get_redis` 헬퍼

- `app/models/*.py`
  - `ShuttleRoute`, `Schedule`, `Camera`, `RouteCameraMapping`, `Sighting` 등  
    셔틀/시간표/카메라/감지이력 스키마 정의

- `app/services/stream_manager.py`
  - 각 카메라 상태(`SNAPSHOT` / `STREAM` / `IDLE`)와  
    **최대 동시 스트림 개수**를 관리하는 매니저

- `app/services/bus_detector.py`
  - YOLOv8 ONNX를 로딩하고, 이미지/프레임에서 **bus class**만 감지
  - confidence threshold, NMS 등 후처리 포함

- `app/services/route_matcher.py`
  - 현재 시간, 카메라 위치, 과거 감지 이력에 기반해  
    “지금 보인 버스가 어떤 노선·어떤 출발 편성인지” 점수화하여 선택

- `app/services/location_estimator.py`
  - 마지막 감지 카메라 이후 경과 시간 + 평균 속도를 이용해  
    노선 폴리라인 위의 현재 위치를 보간  
  - Redis에 위치 저장 및 Pub/Sub 발행

- `app/services/scheduler.py`
  - 위 모든 서비스를 조합한 **메인 스케줄러 루프**  
  - SNAPSHOT/STREAM 모드 전환, 감지 파이프라인 실행, 다음 카메라 활성화 등 orchestration

- `app/api/*.py`
  - `routes.py` : 노선/시간표 REST API
  - `location.py` : Redis 기반 버스 위치 REST API
  - `ws.py` : Redis Pub/Sub 기반 WebSocket endpoint

- `scripts/seed_data.py`
  - 호서대 아산·천안 캠퍼스 사이 노선/시간표를 코드 상에 정의하고 DB에 seed
  - 네이버 길찾기 API를 이용해 실제 도로 경로 폴리라인으로 치환 가능(`--naver`)

- `scripts/fetch_cameras.py`
  - ITS/UTIC CCTV 목록을 가져와, 노선 폴리라인에 **가까운 카메라 자동 선택 및 매핑**

---

## 3. 클라이언트 (`bus_client`) 상세

### 3.1 사용 기술

- Flutter (Material 3)
- 상태 관리: **Riverpod**
- 네트워크: Dio (REST), `web_socket_channel` (WebSocket)
- 라우팅: go_router
- 지도: flutter_naver_map (현재는 placeholder 중심, 실제 지도 연동 전 단계)

### 3.2 주요 화면

- `HomeScreen`
  - 상단: 지도 자리(현재는 “Naver Map이 여기에 표시됩니다” 플레이스홀더)
  - 하단: 현재 운행 중인 셔틀 리스트
    - 노선 ID, 신뢰도(색상으로 표시), 마지막 갱신 시각, 위도/경도
    - 항목 탭 시 해당 노선 상세 화면으로 이동

- `RouteListScreen`
  - `/api/routes` 로부터 노선 목록을 불러와 리스트로 표시
  - 노선 색상(원형 아이콘), 노선명, 캠퍼스(아산/천안) 표기

- `RouteDetailScreen`
  - 특정 노선의 경로(지도 placeholder) + 해당 노선 시간표
  - `RouteSchedule`를 노선별로 정렬해 보여줌

- `ScheduleScreen`
  - 평일/토요일/공휴일 버튼으로 요일을 바꿔가며 전체 시간표를 조회
  - 노선별로 시간을 Chip 형태로 그룹화

### 3.3 데이터 흐름 (요약)

- `lib/services/api_service.dart`
  - `/api/routes`, `/api/schedules`, `/buses/location` 등의 REST 호출 담당
  - 응답 JSON을 `ShuttleRoute`, `Schedule`, `BusLocation` 모델로 변환

- `lib/services/websocket_service.dart`
  - `/ws/location` 또는 `/ws/location/{route_id}`에 WebSocket 연결  
  - 서버에서 오는 버스 위치 업데이트를 스트림으로 노출

- `lib/providers/*`
  - `busLocationsProvider` :  
    - 초기에 REST로 한 번 전체 위치를 가져오고,  
    - 이후 WebSocket 스트림으로 들어오는 업데이트를 **머지**하여  
      항상 최신 버스 위치 리스트를 유지
  - `routeListProvider`, `routeDetailProvider`, `scheduleListProvider` 등은  
    필요한 시점에 REST 호출을 트리거하는 FutureProvider

---

## 4. 필요 환경

### 4.1 공통

- OS: Windows / macOS / Linux
- Git, Python 3.10+, Docker(선택), Flutter SDK(앱 실행 시)

### 4.2 백엔드 (`bus_server`)

- Python 3.10 이상
- PostgreSQL 16 (docker-compose 사용 시 자동 설치)
- Redis 7 (docker-compose 사용 시 자동 설치)
- GPU가 있다면 YOLO 추론 속도에 도움 (필수는 아님)

필수 Python 패키지는 `bus_server/requirements.txt` 참고.

### 4.3 클라이언트 (`bus_client`)

- Flutter SDK (3.x 이상 권장)
- Android Studio 또는 VSCode + Flutter/Dart 플러그인
- 실제 지도 연동 시 Naver Map API 키 필요

---

## 5. 실행 방법 (요약)

### 5.1 백엔드만 빠르게 띄우기 (Docker)

```bash
cd bus_server
docker compose up --build
```

- API: `http://localhost:8000`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`

### 5.2 로컬 개발 환경에서 실행

```bash
cd bus_server
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt

# .env 파일을 .env.example 참고해 작성한 뒤
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 5.3 초기 데이터 세팅 (필수)

```bash
cd bus_server

# 1) 노선/시간표 시드
python -m scripts.seed_data

# 2) CCTV 카메라 수집 및 노선 매핑
python -m scripts.fetch_cameras
```

위 두 스텝을 한번 실행해 두어야 노선·시간표·카메라 정보가 DB에 채워지고,  
