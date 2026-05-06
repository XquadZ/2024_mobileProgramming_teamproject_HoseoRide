import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Sighting(Base):
    """A record of a bus being detected at a camera location."""

    __tablename__ = "sightings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    camera_id: Mapped[int] = mapped_column(Integer, index=True)
    route_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(Float)
    # Inferred shuttle trip identifier (schedule_id + departure sequence)
    trip_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    detected_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    led_text: Mapped[str | None] = mapped_column(String(100), nullable=True)
