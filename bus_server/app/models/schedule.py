from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route_id: Mapped[int] = mapped_column(Integer, index=True)
    departure_time: Mapped[str] = mapped_column(String(5))  # "HH:MM" format
    day_type: Mapped[str] = mapped_column(String(20), default="weekday")  # weekday, saturday, holiday
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
