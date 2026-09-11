from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Mapping
from uuid import uuid4


class EventType(StrEnum):
    USER_INPUT = "user_input"
    THINKING_STARTED = "thinking_started"
    RESPONSE_STARTED = "response_started"
    RESPONSE_FINISHED = "response_finished"
    INTERRUPT = "interrupt"
    MEMORY_APPROVED = "memory_approved"
    MEMORY_REJECTED = "memory_rejected"
    MUTE_CHANGED = "mute_changed"
    NETWORK_CHANGED = "network_changed"
    BATTERY_CHANGED = "battery_changed"
    LOW_BATTERY = "low_battery"
    TOUCH = "touch"
    COLLISION = "collision"
    ERROR = "error"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True, slots=True)
class RobotEvent:
    type: EventType
    payload: Mapping[str, object] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


