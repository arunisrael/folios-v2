"""Shared type aliases for the domain layer."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, NewType
from uuid import UUID

StrategyId = NewType("StrategyId", UUID)
RequestId = NewType("RequestId", UUID)
TaskId = NewType("TaskId", UUID)
RunId = NewType("RunId", UUID)
DigestId = NewType("DigestId", UUID)
PositionSnapshotId = NewType("PositionSnapshotId", UUID)
PositionId = NewType("PositionId", UUID)
OrderId = NewType("OrderId", UUID)
JsonMapping = Mapping[str, Any]
IsoWeek = tuple[int, int]
DateLike = date | datetime

__all__ = [
    "DateLike",
    "DigestId",
    "IsoWeek",
    "JsonMapping",
    "OrderId",
    "PositionId",
    "PositionSnapshotId",
    "RequestId",
    "RunId",
    "StrategyId",
    "TaskId",
]
