# Project Guidelines

## Architecture
This workspace is a two-part monorepo:

- `bus_server`: FastAPI backend with async SQLAlchemy, PostgreSQL, Redis pub/sub, CCTV polling, YOLO-based bus detection, and a scheduler started from the FastAPI lifespan.
- `bus_client`: Flutter app using Riverpod, GoRouter, Dio, and WebSocket updates from the backend.

Backend and frontend communicate through REST endpoints under `/api` and WebSocket endpoints under `/ws`.

## Build and Test
Use the repo root virtual environment for Python work on Windows: `c:/flutterproj/bustracker/.venv/Scripts/python.exe`.

Backend commands:

- Install dependencies: `c:/flutterproj/bustracker/.venv/Scripts/python.exe -m pip install -r bus_server/requirements.txt`
- Run API locally: `cd bus_server && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- Start local infrastructure: `cd bus_server && docker-compose up -d`
- Seed routes and schedules: `cd bus_server && c:/flutterproj/bustracker/.venv/Scripts/python.exe -m scripts.seed_data --naver`
- Fetch and map CCTV cameras: `cd bus_server && c:/flutterproj/bustracker/.venv/Scripts/python.exe -m scripts.fetch_cameras`
- Lint backend changes: `cd bus_server && c:/flutterproj/bustracker/.venv/Scripts/python.exe -m ruff check .`

Frontend commands:

- Install dependencies: `cd bus_client && flutter pub get`
- Run app: `cd bus_client && flutter run`
- Analyze after Dart changes: `cd bus_client && flutter analyze`
- Run tests: `cd bus_client && flutter test`

## Conventions
- Keep backend code async end-to-end. Use `AsyncSession`, async context managers, and avoid sync database access.
- Keep timezone handling aligned with Korea time (`UTC+9`) when working with schedules, detections, and bus location timestamps.
- Preserve the current service pipeline design: CCTV input -> bus detection -> route matching -> location estimation -> Redis publish.
- Keep dependency manifests unpinned unless the task explicitly requires a version constraint. This repository intentionally omits most version pins.
- Do not commit local secrets or generated model artifacts. `.env`, `.onnx`, and `.pt` files are treated as local/runtime assets.
- When changing backend behavior, prefer small targeted changes in `app/services/` and keep API contracts stable for the Flutter client.
- When changing frontend code, follow the existing Riverpod providers, model classes, and GoRouter structure under `lib/core`, `lib/providers`, `lib/services`, and `lib/screens`.

## Key Files
- Backend entrypoint: `bus_server/app/main.py`
- Backend scheduler orchestration: `bus_server/app/services/scheduler.py`
- Backend route and location APIs: `bus_server/app/api/routes.py`, `bus_server/app/api/location.py`, `bus_server/app/api/ws.py`
- Frontend app shell: `bus_client/lib/app.dart`
- Frontend API integration: `bus_client/lib/services/api_service.dart`, `bus_client/lib/services/websocket_service.dart`