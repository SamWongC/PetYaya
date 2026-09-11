from __future__ import annotations

from collections import deque
from collections.abc import Mapping

from pet_yaya.domain.events import EventType, RobotEvent
from pet_yaya.domain.session import (
    SessionSnapshot,
    SessionState,
    VirtualDeviceState,
)


class InteractionBlockedError(RuntimeError):
    """Raised when the current session state cannot accept user input."""


class InvalidStateTransitionError(RuntimeError):
    """Raised when internal workflow events arrive in an invalid order."""


class SessionManager:
    """Deterministic state machine and bounded in-memory event history."""

    def __init__(self, event_history_limit: int = 200) -> None:
        self._state = SessionState.IDLE
        self._device = VirtualDeviceState()
        self._last_error: str | None = None
        self._events: deque[RobotEvent] = deque(maxlen=event_history_limit)

    def dispatch(
        self,
        event_type: EventType,
        payload: Mapping[str, object] | None = None,
    ) -> RobotEvent:
        event = RobotEvent(type=event_type, payload=payload or {})
        self._events.append(event)
        self._apply(event)
        return event

    def snapshot(self) -> SessionSnapshot:
        return SessionSnapshot(
            state=self._state,
            muted=self._device.muted,
            online=self._device.online,
            battery_percent=self._device.battery_percent,
            last_error=self._last_error,
        )

    def event_history(self) -> tuple[RobotEvent, ...]:
        return tuple(self._events)

    def _baseline_state(self) -> SessionState:
        if self._device.muted:
            return SessionState.MUTED
        if not self._device.online:
            return SessionState.OFFLINE
        return SessionState.IDLE

    def _apply(self, event: RobotEvent) -> None:
        event_type = event.type

        if event_type is EventType.MUTE_CHANGED:
            self._device.muted = bool(event.payload.get("muted", False))
            self._state = self._baseline_state()
            return

        if event_type is EventType.NETWORK_CHANGED:
            self._device.online = bool(event.payload.get("online", True))
            self._state = self._baseline_state()
            return

        if event_type in {EventType.BATTERY_CHANGED, EventType.LOW_BATTERY}:
            raw_percent = int(event.payload.get("percent", 0))
            self._device.battery_percent = max(0, min(raw_percent, 100))
            return

        if event_type is EventType.USER_INPUT:
            if self._device.muted:
                raise InteractionBlockedError(
                    "麦克风已静音，请先输入 /unmute。"
                )
            if self._state is SessionState.AWAITING_CONFIRMATION:
                raise InteractionBlockedError(
                    "请先输入 /yes 或 /no 处理当前记忆。"
                )
            if self._state in {
                SessionState.LISTENING,
                SessionState.THINKING,
                SessionState.SPEAKING,
            }:
                raise InteractionBlockedError("Yaya 正在处理上一条消息。")
            self._last_error = None
            self._state = SessionState.LISTENING
            return

        if event_type is EventType.THINKING_STARTED:
            self._require_state(SessionState.LISTENING, event_type)
            self._state = SessionState.THINKING
            return

        if event_type is EventType.RESPONSE_STARTED:
            self._require_state(SessionState.THINKING, event_type)
            self._state = SessionState.SPEAKING
            return

        if event_type is EventType.RESPONSE_FINISHED:
            self._require_state(SessionState.SPEAKING, event_type)
            if bool(event.payload.get("awaiting_confirmation", False)):
                self._state = SessionState.AWAITING_CONFIRMATION
            else:
                self._state = self._baseline_state()
            return

        if event_type in {
            EventType.MEMORY_APPROVED,
            EventType.MEMORY_REJECTED,
            EventType.INTERRUPT,
        }:
            self._state = self._baseline_state()
            return

        if event_type is EventType.COLLISION:
            self._state = self._baseline_state()
            return

        if event_type is EventType.ERROR:
            self._last_error = str(
                event.payload.get("message", "unknown error")
            )
            self._state = SessionState.ERROR
            return

        if event_type is EventType.SHUTDOWN:
            self._state = self._baseline_state()
            return

        # TOUCH is deliberately observational and does not change the state.

    def _require_state(
        self, expected: SessionState, event_type: EventType
    ) -> None:
        if self._state is not expected:
            raise InvalidStateTransitionError(
                f"Cannot apply {event_type.value} while state is "
                f"{self._state.value}; expected {expected.value}."
            )


