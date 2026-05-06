from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(20))  # "utic" or "its"
    name: Mapped[str] = mapped_column(String(200))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    road_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    stream_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_url: Mapped[str | None] = mapped_column(Text, nullable=True)
