from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from pet_yaya.adapters.simulator import (  # noqa: E402
    ConservativeSafetyPolicy,
    RuleBasedDialogueEngine,
)
from pet_yaya.application.orchestrator import PetYayaOrchestrator  # noqa: E402
from pet_yaya.domain.models import ActionCommand, ActionName, Emotion  # noqa: E402
from pet_yaya.infrastructure.in_memory import (  # noqa: E402
    InMemoryGrowthRepository,
    InMemoryMemoryRepository,
    InMemoryPendingMemoryRepository,
)
from pet_yaya.main import resolve_memory_id  # noqa: E402


class RecordingActuator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Emotion, ActionCommand]] = []

    def present(
        self, speech: str, emotion: Emotion, action: ActionCommand
    ) -> None:
        self.calls.append((speech, emotion, action))


def build_test_subject() -> tuple[
    PetYayaOrchestrator, RecordingActuator, InMemoryMemoryRepository
]:
    actuator = RecordingActuator()
    memories = InMemoryMemoryRepository()
    subject = PetYayaOrchestrator(
        dialogue=RuleBasedDialogueEngine(),
        memories=memories,
        pending_memories=InMemoryPendingMemoryRepository(),
        growth_repository=InMemoryGrowthRepository(),
        safety=ConservativeSafetyPolicy(),
        actuator=actuator,
    )
    return subject, actuator, memories


class OrchestratorTests(unittest.TestCase):
    def test_explicit_requests_do_not_depend_on_model(self) -> None:
        from unittest.mock import Mock

        for text in ("请记住，我的名字是小明", "请记住，我是你的开发者", "记住我喜欢恐龙"):
            with self.subTest(text=text):
                subject, _, memories = build_test_subject()
                subject._dialogue = Mock()
                subject._dialogue.respond.side_effect = AssertionError("Model must not be called")
                result = subject.interact(text)
                self.assertIsNotNone(result.pending_memory_id)
                self.assertIn("我可以记住这件事吗", result.speech)
                self.assertEqual(memories.list_all(), ())
                subject.confirm_memory(result.pending_memory_id, True)
                self.assertEqual(len(memories.list_all()), 1)
                self.assertEqual(memories.list_all()[0].source, "explicit_user_request")
                self.assertIn(memories.list_all()[0].content, result.speech)

    def test_explicit_request_rejection_does_not_save(self) -> None:
        subject, _, memories = build_test_subject()
        result = subject.interact("请记住，我的名字是小明")
        self.assertTrue(subject.confirm_memory(result.pending_memory_id, False))
        self.assertEqual(memories.list_all(), ())
        self.assertFalse(subject.confirm_memory(result.pending_memory_id, True))

    def test_empty_long_and_sensitive_requests_do_not_create_candidates(self) -> None:
        for text in ("请记住", "记住：", "请记住" + "字" * 201, "请记住我的密码是abc123"):
            with self.subTest(text=text):
                subject, _, memories = build_test_subject()
                result = subject.interact(text)
                self.assertIsNone(result.pending_memory_id)
                self.assertEqual(memories.list_all(), ())

    def test_negation_and_quoted_requests_are_not_explicit_commands(self) -> None:
        from pet_yaya.domain.memory_requests import explicit_memory_request

        self.assertIsNone(explicit_memory_request("不要记住我的名字").memory_candidate)
        for text in ("他说：请记住我", "你能记住什么？"):
            self.assertIsNone(explicit_memory_request(text))

    def test_normal_interaction_updates_growth_and_actuates(self) -> None:
        subject, actuator, _ = build_test_subject()

        result = subject.interact("你好")

        self.assertEqual(result.emotion, Emotion.HAPPY)
        self.assertEqual(len(actuator.calls), 1)
        self.assertEqual(subject.growth_state().interaction_count, 1)

    def test_memory_is_not_persisted_before_confirmation(self) -> None:
        subject, _, memories = build_test_subject()

        result = subject.interact("我喜欢恐龙")

        self.assertIsNotNone(result.pending_memory_id)
        self.assertEqual(memories.list_all(), ())

    def test_confirmed_memory_is_persisted(self) -> None:
        subject, _, memories = build_test_subject()
        result = subject.interact("我喜欢恐龙")

        handled = subject.confirm_memory(result.pending_memory_id or "", True)

        self.assertTrue(handled)
        self.assertEqual(len(memories.list_all()), 1)
        self.assertIn("恐龙", memories.list_all()[0].content)

    def test_rejected_memory_is_not_persisted(self) -> None:
        subject, _, memories = build_test_subject()
        result = subject.interact("记住星期天画画")

        handled = subject.confirm_memory(result.pending_memory_id or "", False)

        self.assertTrue(handled)
        self.assertEqual(memories.list_all(), ())

    def test_safety_policy_replaces_unknown_action(self) -> None:
        safety = ConservativeSafetyPolicy()

        action, adjusted = safety.approve_action(
            ActionCommand("drive_at_full_speed", 10.0)
        )

        self.assertTrue(adjusted)
        self.assertEqual(action.name, ActionName.IDLE)
        self.assertEqual(action.intensity, 0.0)

    def test_growth_unlocks_skill_at_threshold(self) -> None:
        subject, _, _ = build_test_subject()

        for _ in range(3):
            subject.interact("你好")

        self.assertIn(
            "curious_greeting", subject.growth_state().unlocked_skills
        )

    def test_memory_list_number_resolves_to_memory_id(self) -> None:
        subject, _, memories = build_test_subject()
        result = subject.interact("我喜欢恐龙")
        subject.confirm_memory(result.pending_memory_id or "", True)
        saved = memories.list_all()

        resolved = resolve_memory_id("1", saved)

        self.assertEqual(resolved, saved[0].id)

    def test_invalid_memory_list_number_does_not_resolve(self) -> None:
        subject, _, memories = build_test_subject()
        result = subject.interact("我喜欢恐龙")
        subject.confirm_memory(result.pending_memory_id or "", True)

        self.assertIsNone(resolve_memory_id("2", memories.list_all()))


if __name__ == "__main__":
    unittest.main()

