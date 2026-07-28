"""Data contract for a future native Apple RoomPlan companion or App Clip."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Vector3(BaseModel):
    x: float
    y: float
    z: float


class RoomPlane(BaseModel):
    position_m: Vector3
    normal: Vector3


class RoomWall(BaseModel):
    id: str
    width_m: float = Field(gt=0)
    height_m: float = Field(gt=0)
    position_m: Vector3
    normal: Vector3


class RoomOpening(BaseModel):
    id: str
    kind: Literal["door", "window", "opening"]
    width_m: float = Field(gt=0)
    height_m: float = Field(gt=0)
    position_m: Vector3


class RoomPlanCapture(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    source: Literal["apple_roomplan"] = "apple_roomplan"
    capture_id: str
    room_width_m: float = Field(gt=0)
    room_length_m: float = Field(gt=0)
    room_height_m: float = Field(gt=0)
    floor_plane: RoomPlane
    walls: list[RoomWall] = Field(default_factory=list)
    openings: list[RoomOpening] = Field(default_factory=list)


def model_payload(model: BaseModel) -> dict:
    """Support both Pydantic 1 and 2 while the FastAPI range remains broad."""
    dump = getattr(model, "model_dump", None)
    return dump(mode="json") if dump else model.dict()
