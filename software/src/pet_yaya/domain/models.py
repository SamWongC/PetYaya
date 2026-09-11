from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4


class Emotion(StrEnum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    CURIOUS = "curious"
    CALM = "calm"
    SLEEPY = "sleepy"


class ActionName(StrEnum):
    IDLE = "idle"
    NOD = "nod"
    TILT_HEAD = "tilt_head"
    LOOK_LEFT_RIGHT = "look_left_right"
    HAPPY_WIGGLE = "happy_wiggle"
    SLEEP_POSE = "sleep_pose"


@dataclass(frozen=True, slots=True)
class ActionCommand:
    name: str
    intensity: float = 0.5


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    category: str
    content: str
    source: str = "user_statement"
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass(frozen=True, slots=True)
class ConfirmedMemory:
    id: str
    category: str
    content: str
    source: str
    created_at: datetime
    confirmed_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @classmethod
    def from_candidate(cls, candidate: MemoryCandidate) -> "ConfirmedMemory":
        return cls(
            id=candidate.id,
            category=candidate.category,
            content=candidate.content,
            source=candidate.source,
            created_at=candidate.created_at,
        )


@dataclass(frozen=True, slots=True)
class DialogueTurn:
    user_text: str
    assistant_text: str


@dataclass(frozen=True, slots=True)
class DialogueContext:
    memories: tuple[ConfirmedMemory, ...]
    interaction_count: int
    unlocked_skills: tuple[str, ...]
    recent_turns: tuple[DialogueTurn, ...] = ()


@dataclass(frozen=True, slots=True)
class DialogueResult:
    speech: str
    emotion: Emotion = Emotion.NEUTRAL
    action: ActionCommand = field(
        default_factory=lambda: ActionCommand(ActionName.IDLE)
    )
    memory_candidate: MemoryCandidate | None = None
    action_adjusted: bool = False


@dataclass(slots=True)
class GrowthState:
    interaction_count: int = 0
    growth_points: int = 0
    unlocked_skills: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class InteractionResult:
    speech: str
    emotion: Emotion
    action: ActionCommand
    pending_memory_id: str | None
    safety_adjusted: bool


@dataclass(frozen=True, slots=True)
class DialogueEngineStatus:
    mode: str
    active_provider: str
    model: str | None
    configured: bool
    last_error: str | None = None

