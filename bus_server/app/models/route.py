from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ShuttleRoute(Base):
    __tablename__ = "shuttle_routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))  # e.g. "아산→천안", "천안→아산"
    campus: Mapped[str] = mapped_column(String(50))  # "asan" or "cheonan"
    direction: Mapped[str] = mapped_column(String(20))  # "outbound" or "inbound"
    # Ordered list of lat,lng pairs as JSON string: [[lat,lng], [lat,lng], ...]
    waypoints_json: Mapped[str] = mapped_column(Text)
    color: Mapped[str] = mapped_column(String(10), default="#1976D2")


class RouteCameraMapping(Base):
    """Maps cameras to routes with ordering — which cameras cover a route and in what sequence."""

    __tablename__ = "route_camera_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route_id: Mapped[int] = mapped_column(Integer, index=True)
    camera_id: Mapped[int] = mapped_column(Integer, index=True)
    sequence_order: Mapped[int] = mapped_column(Integer)
    # Expected travel time in seconds from route start to this camera
    expected_seconds_from_start: Mapped[float] = mapped_column(Float, default=0.0)
