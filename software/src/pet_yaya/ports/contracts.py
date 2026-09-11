from __future__ import annotations

from typing import Protocol

from pet_yaya.domain.models import (
    ActionCommand,
    ConfirmedMemory,
    DialogueContext,
    DialogueResult,
    Emotion,
    GrowthState,
    MemoryCandidate,
)


class DialogueEngine(Protocol):
    def respond(self, text: str, context: DialogueContext) -> DialogueResult:
        """Create a proposed response without causing side effects."""


class MemoryRepository(Protocol):
    def list_all(self) -> tuple[ConfirmedMemory, ...]: ...

    def save(self, memory: ConfirmedMemory) -> None: ...

    def delete(self, memory_id: str) -> bool: ...

    def clear(self) -> None: ...


class PendingMemoryRepository(Protocol):
    def save(self, candidate: MemoryCandidate) -> None: ...

    def get(self, memory_id: str) -> MemoryCandidate | None: ...

    def remove(self, memory_id: str) -> MemoryCandidate | None: ...

    def clear(self) -> None: ...


class GrowthRepository(Protocol):
    def get(self) -> GrowthState: ...

    def save(self, state: GrowthState) -> None: ...

    def reset(self) -> None: ...


class SafetyPolicy(Protocol):
    def approve_action(self, action: ActionCommand) -> tuple[ActionCommand, bool]:
        """Return the safe action and whether the proposal was adjusted."""


class Actuator(Protocol):
    def present(
        self, speech: str, emotion: Emotion, action: ActionCommand
    ) -> None:
        """Present speech, expression and motion through a device or simulator."""

