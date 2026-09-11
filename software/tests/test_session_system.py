from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from pet_yaya.application.session_manager import (  # noqa: E402
    InteractionBlockedError,
    InvalidStateTransitionError,
    SessionManager,
)
from pet_yaya.bootstrap import build_simulator  # noqa: E402
from pet_yaya.config import DialogueSettings  # noqa: E402
from pet_yaya.domain.events import EventType  # noqa: E402
from pet_yaya.domain.models import ActionCommand, ActionName, Emotion  # noqa: E402
from pet_yaya.domain.session import SessionState  # noqa: E402


class RecordingActuator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Emotion, ActionCommand]] = []

    def present(
        self, speech: str, emotion: Emotion, action: ActionCommand
    ) -> None:
        self.calls.append((speech, emotion, action))


class FailingActuator:
    def present(
        self, speech: str, emotion: Emotion, action: ActionCommand
    ) -> None:
        raise RuntimeError("simulated actuator failure")


class SessionSystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self._temporary_directory.name) / "state.db"
        self.actuator = RecordingActuator()
        self.yaya = build_simulator(
            self.database_path,
            self.actuator,
            dialogue_settings=DialogueSettings(mode="rules"),
        )

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def test_normal_interaction_returns_to_idle_and_records_events(self) -> None:
        self.yaya.interact("你好")

        self.assertEqual(
            self.yaya.session_status().state, SessionState.IDLE
        )
        event_types = [event.type for event in self.yaya.event_history()]
        self.assertEqual(
            event_types,
            [
                EventType.USER_INPUT,
                EventType.THINKING_STARTED,
                EventType.RESPONSE_STARTED,
                EventType.RESPONSE_FINISHED,
            ],
        )
        self.assertNotIn(
            "你好",
            " ".join(
                str(event.payload) for event in self.yaya.event_history()
            ),
        )

    def test_memory_candidate_waits_for_confirmation(self) -> None:
        result = self.yaya.interact("我喜欢恐龙")

        self.assertEqual(
            self.yaya.session_status().state,
            SessionState.AWAITING_CONFIRMATION,
        )

        self.yaya.confirm_memory(result.pending_memory_id or "", True)

        self.assertEqual(
            self.yaya.session_status().state, SessionState.IDLE
        )
        self.assertEqual(
            self.yaya.event_history()[-1].type,
            EventType.MEMORY_APPROVED,
        )

    def test_muted_state_blocks_input_but_status_remains_available(self) -> None:
        self.yaya.set_muted(True)

        with self.assertRaises(InteractionBlockedError):
            self.yaya.interact("你好")

        status = self.yaya.session_status()
        self.assertEqual(status.state, SessionState.MUTED)
        self.assertTrue(status.muted)
        self.assertEqual(self.yaya.growth_state().interaction_count, 0)

    def test_offline_mode_keeps_local_dialogue_available(self) -> None:
        self.yaya.set_online(False)

        result = self.yaya.interact("你好")

        self.assertIn("你好", result.speech)
        self.assertEqual(
            self.yaya.session_status().state, SessionState.OFFLINE
        )

    def test_low_battery_replaces_motion_with_idle(self) -> None:
        self.yaya.set_battery(10)

        result = self.yaya.interact("你好")

        self.assertEqual(result.action.name, ActionName.IDLE)
        self.assertEqual(result.action.intensity, 0.0)
        self.assertTrue(result.safety_adjusted)

    def test_touch_and_collision_are_recorded(self) -> None:
        self.yaya.touch()
        self.yaya.collision()

        event_types = [event.type for event in self.yaya.event_history()]

        self.assertIn(EventType.TOUCH, event_types)
        self.assertEqual(event_types[-1], EventType.COLLISION)
        self.assertEqual(
            self.yaya.session_status().state, SessionState.IDLE
        )

    def test_invalid_internal_transition_is_rejected(self) -> None:
        session = SessionManager()

        with self.assertRaises(InvalidStateTransitionError):
            session.dispatch(EventType.RESPONSE_STARTED)

    def test_interrupt_returns_active_response_to_safe_baseline(self) -> None:
        session = SessionManager()
        session.dispatch(EventType.USER_INPUT)
        session.dispatch(EventType.THINKING_STARTED)
        session.dispatch(EventType.RESPONSE_STARTED)

        session.dispatch(EventType.INTERRUPT)

        self.assertEqual(session.snapshot().state, SessionState.IDLE)

    def test_reset_leaves_session_ready_for_new_input(self) -> None:
        self.yaya.interact("我喜欢恐龙")

        self.yaya.reset_state()
        result = self.yaya.interact("你好")

        self.assertIn("你好", result.speech)
        self.assertEqual(
            self.yaya.session_status().state, SessionState.IDLE
        )

    def test_runtime_failure_enters_error_state_without_damaging_database(
        self,
    ) -> None:
        failing_yaya = build_simulator(
            self.database_path,
            FailingActuator(),
            dialogue_settings=DialogueSettings(mode="rules"),
        )

        with self.assertRaisesRegex(
            RuntimeError, "simulated actuator failure"
        ):
            failing_yaya.interact("你好")

        self.assertEqual(
            failing_yaya.session_status().state, SessionState.ERROR
        )
        self.assertIn(
            "simulated actuator failure",
            failing_yaya.session_status().last_error or "",
        )

        reloaded = build_simulator(
            self.database_path,
            self.actuator,
            dialogue_settings=DialogueSettings(mode="rules"),
        )
        self.assertEqual(reloaded.growth_state().interaction_count, 1)


if __name__ == "__main__":
    unittest.main()

