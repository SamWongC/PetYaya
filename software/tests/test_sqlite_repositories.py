from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from pet_yaya.bootstrap import build_simulator  # noqa: E402
from pet_yaya.config import DialogueSettings  # noqa: E402
from pet_yaya.domain.models import (  # noqa: E402
    ConfirmedMemory,
    GrowthState,
    MemoryCandidate,
)
from pet_yaya.infrastructure.sqlite import (  # noqa: E402
    SQLiteDatabase,
    SQLiteGrowthRepository,
    SQLiteMemoryRepository,
    SQLitePendingMemoryRepository,
)


class SilentActuator:
    def present(self, speech: str, emotion: object, action: object) -> None:
        pass


class SQLiteRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self._temporary_directory.name) / "state.db"
        self.database = SQLiteDatabase(self.database_path)

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def test_confirmed_memory_survives_repository_recreation(self) -> None:
        first = SQLiteMemoryRepository(self.database)
        candidate = MemoryCandidate(
            category="preference", content="主人喜欢恐龙"
        )
        first.save(ConfirmedMemory.from_candidate(candidate))

        second_database = SQLiteDatabase(self.database_path)
        second = SQLiteMemoryRepository(second_database)

        self.assertEqual(len(second.list_all()), 1)
        self.assertEqual(second.list_all()[0].content, "主人喜欢恐龙")

    def test_pending_memory_can_be_removed_atomically(self) -> None:
        repository = SQLitePendingMemoryRepository(self.database)
        candidate = MemoryCandidate(category="fact", content="星期天画画")
        repository.save(candidate)

        removed = repository.remove(candidate.id)

        self.assertEqual(removed, candidate)
        self.assertIsNone(repository.get(candidate.id))

    def test_growth_survives_repository_recreation(self) -> None:
        first = SQLiteGrowthRepository(self.database)
        first.save(
            GrowthState(
                interaction_count=8,
                growth_points=8,
                unlocked_skills=["curious_greeting", "tiny_story"],
            )
        )

        second = SQLiteGrowthRepository(SQLiteDatabase(self.database_path))

        self.assertEqual(second.get().interaction_count, 8)
        self.assertIn("tiny_story", second.get().unlocked_skills)

    def test_full_reset_clears_persistent_state(self) -> None:
        yaya = build_simulator(
            self.database_path,
            actuator=SilentActuator(),
            dialogue_settings=DialogueSettings(mode="rules"),
        )
        result = yaya.interact("我喜欢恐龙")
        yaya.confirm_memory(result.pending_memory_id or "", True)

        yaya.reset_state()
        reloaded = build_simulator(
            self.database_path,
            actuator=SilentActuator(),
            dialogue_settings=DialogueSettings(mode="rules"),
        )

        self.assertEqual(reloaded.list_memories(), ())
        self.assertEqual(reloaded.growth_state().interaction_count, 0)


if __name__ == "__main__":
    unittest.main()

