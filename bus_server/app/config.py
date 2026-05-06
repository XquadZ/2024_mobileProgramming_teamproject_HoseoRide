from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    app_name: str = "BusTracker API"
    debug: bool = Field(default=False, alias="APP_DEBUG")

    # Database
    database_url: str = "postgresql+asyncpg://bustracker:bustracker@localhost:5432/bustracker"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # UTIC API
    utic_api_key: str = ""
    utic_base_url: str = "http://www.utic.go.kr"

    # ITS (국가교통정보센터) API
    its_api_key: str = ""
    its_base_url: str = "https://openapi.its.go.kr:9443"

    # CCTV Polling
    snapshot_interval_seconds: int = 7
    max_concurrent_streams: int = 3

    # YOLO
    yolo_model_path: str = "yolov8n.onnx"
    yolo_confidence_threshold: float = 0.4
    bus_class_id: int = 5  # COCO 'bus' class

    # Naver Map API (Directions)
    naver_client_id: str = ""
    naver_client_secret: str = ""

    # Location estimation
    default_bus_speed_kmh: float = 40.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
