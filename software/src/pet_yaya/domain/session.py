from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SessionState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    MUTED = "muted"
    OFFLINE = "offline"
    ERROR = "error"


@dataclass(slots=True)
class VirtualDeviceState:
    muted: bool = False
    online: bool = True
    battery_percent: int = 100


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    state: SessionState
    muted: bool
    online: bool
    battery_percent: int
    last_error: str | None


