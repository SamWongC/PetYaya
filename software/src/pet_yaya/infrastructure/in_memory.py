from __future__ import annotations

from copy import deepcopy

from pet_yaya.domain.models import ConfirmedMemory, GrowthState, MemoryCandidate


class InMemoryMemoryRepository:
    def __init__(self) -> None:
        self._items: dict[str, ConfirmedMemory] = {}

    def list_all(self) -> tuple[ConfirmedMemory, ...]:
        return tuple(self._items.values())

    def save(self, memory: ConfirmedMemory) -> None:
        self._items[memory.id] = memory

    def delete(self, memory_id: str) -> bool:
        return self._items.pop(memory_id, None) is not None

    def clear(self) -> None:
        self._items.clear()


class InMemoryPendingMemoryRepository:
    def __init__(self) -> None:
        self._items: dict[str, MemoryCandidate] = {}

    def save(self, candidate: MemoryCandidate) -> None:
        self._items[candidate.id] = candidate

    def get(self, memory_id: str) -> MemoryCandidate | None:
        return self._items.get(memory_id)

    def remove(self, memory_id: str) -> MemoryCandidate | None:
        return self._items.pop(memory_id, None)

    def clear(self) -> None:
        self._items.clear()


class InMemoryGrowthRepository:
    def __init__(self) -> None:
        self._state = GrowthState()

    def get(self) -> GrowthState:
        return deepcopy(self._state)

    def save(self, state: GrowthState) -> None:
        self._state = deepcopy(state)

    def reset(self) -> None:
        self._state = GrowthState()

