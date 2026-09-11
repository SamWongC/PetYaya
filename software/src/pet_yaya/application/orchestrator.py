from __future__ import annotations

from collections import deque
from dataclasses import replace
from pet_yaya.domain.memory_intent import MemoryIntent, looks_like_memory_request
from pet_yaya.domain.voice_confirmation import parse_memory_confirmation
from collections.abc import Callable
from pet_yaya.domain.cancellation import CancellationToken, DialogueCancelled

from pet_yaya.application.session_manager import SessionManager
from pet_yaya.domain.events import EventType, RobotEvent
from pet_yaya.domain.growth import GrowthEngine
from pet_yaya.domain.memory_requests import explicit_memory_request
from pet_yaya.domain.models import (
    ActionCommand,
    ActionName,
    ConfirmedMemory,
    DialogueContext,
    DialogueEngineStatus,
    DialogueTurn,
    Emotion,
    GrowthState,
    InteractionResult,
)
from pet_yaya.domain.session import SessionSnapshot
from pet_yaya.ports.contracts import (
    Actuator,
    DialogueEngine,
    GrowthRepository,
    MemoryRepository,
    PendingMemoryRepository,
    SafetyPolicy,
)


class PetYayaOrchestrator:
    def __init__(
        self,
        dialogue: DialogueEngine,
        memories: MemoryRepository,
        pending_memories: PendingMemoryRepository,
        growth_repository: GrowthRepository,
        safety: SafetyPolicy,
        actuator: Actuator,
        growth_engine: GrowthEngine | None = None,
        session: SessionManager | None = None,
        memory_interpreter=None,
    ) -> None:
        self._dialogue = dialogue
        self._memory_interpreter = memory_interpreter
        self._memories = memories
        self._pending = pending_memories
        self._growth_repository = growth_repository
        self._safety = safety
        self._actuator = actuator
        self._growth_engine = growth_engine or GrowthEngine()
        self._session = session or SessionManager()
        self._recent_turns: deque[DialogueTurn] = deque(maxlen=4)
        self._active_cancellation: CancellationToken | None = None

    def interact(
        self, text: str, on_text: Callable[[str], None] | None = None,
        cancellation: CancellationToken | None = None,
    ) -> InteractionResult:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Interaction text cannot be empty.")

        # Do not place raw conversation text in the event history.
        self._session.dispatch(EventType.USER_INPUT, {"source": "console"})
        token = cancellation or CancellationToken()
        self._active_cancellation = token
        response_started = False

        def preview(chunk):
            nonlocal response_started
            token.check()
            if not response_started:
                self._session.dispatch(EventType.RESPONSE_STARTED)
                response_started = True
            on_text(chunk)

        try:
            token.check()
            self._session.dispatch(EventType.THINKING_STARTED)
            growth = self._growth_repository.get()
            context = DialogueContext(
                memories=self._memories.list_all(),
                interaction_count=growth.interaction_count,
                unlocked_skills=tuple(growth.unlocked_skills),
                recent_turns=tuple(self._recent_turns),
            )
            proposal = explicit_memory_request(cleaned)
            uncertain_memory_intent = False
            if proposal is None and looks_like_memory_request(cleaned):
                precheck = explicit_memory_request("请记住，" + cleaned)
                if precheck is not None and precheck.memory_candidate is None:
                    proposal = precheck
            if proposal is None and self._memory_interpreter is not None and looks_like_memory_request(cleaned):
                intent = self._interpret_memory(cleaned, token)
                uncertain_memory_intent = intent.intent != "request"
                if intent.intent == "request":
                    proposal = explicit_memory_request("请记住，" + intent.content)
                elif looks_like_memory_request(cleaned) and any(word in cleaned for word in ("这个", "这件", "记下来", "存下来")):
                    from pet_yaya.domain.models import DialogueResult
                    proposal = DialogueResult(speech="你想让我记住哪一件事？请再说一下具体内容，我会先确认再保存。")
            if proposal is None:
                stream_method = getattr(self._dialogue, "respond_stream", None)
                if on_text is not None and callable(stream_method):
                    proposal = stream_method(cleaned, context, preview, token)
                else:
                    proposal = self._dialogue.respond(cleaned, context)
            if uncertain_memory_intent:
                proposal = replace(proposal, memory_candidate=None)
            token.check()
            safe_action, adjusted = self._safety.approve_action(proposal.action)

            pending_id = None
            speech = proposal.speech
            if proposal.memory_candidate is not None:
                checked = explicit_memory_request("请记住，" + proposal.memory_candidate.content)
                if checked is None or checked.memory_candidate is None:
                    speech += " 这条内容未通过记忆检查，不会保存。"
                    proposal = replace(proposal, memory_candidate=None)
            if proposal.memory_candidate is not None:
                self._pending.save(proposal.memory_candidate)
                pending_id = proposal.memory_candidate.id
                speech += " 我可以记住这件事吗？"

            updated_growth = self._growth_engine.record_interaction(growth)
            self._growth_repository.save(updated_growth)
            if not response_started:
                self._session.dispatch(EventType.RESPONSE_STARTED)
            self._actuator.present(speech, proposal.emotion, safe_action)
            self._session.dispatch(
                EventType.RESPONSE_FINISHED,
                {"awaiting_confirmation": pending_id is not None},
            )

            # Confirmation exchanges stay out of conversational history.
            if pending_id is None:
                self._recent_turns.append(DialogueTurn(cleaned[:800], speech[:400]))

            return InteractionResult(
                speech=speech,
                emotion=proposal.emotion,
                action=safe_action,
                pending_memory_id=pending_id,
                safety_adjusted=adjusted or proposal.action_adjusted,
            )
        except (KeyboardInterrupt, DialogueCancelled):
            token.cancel()
            self._session.dispatch(EventType.INTERRUPT)
            raise DialogueCancelled("当前回复已停止，未保存本轮生成内容。") from None
        except Exception as error:
            self._session.dispatch(
                EventType.ERROR, {"message": str(error)}
            )
            raise
        finally:
            self._active_cancellation = None

    def confirm_memory(self, memory_id: str, approved: bool) -> bool:
        candidate = self._pending.remove(memory_id)
        if candidate is None:
            return False
        if approved:
            self._memories.save(ConfirmedMemory.from_candidate(candidate))
        self._session.dispatch(
            EventType.MEMORY_APPROVED
            if approved
            else EventType.MEMORY_REJECTED,
            {"memory_id": memory_id},
        )
        return True

    def _interpret_memory(self, text, token, pending=None):
        if self._memory_interpreter is None:
            return MemoryIntent()
        try:
            result = self._memory_interpreter.interpret(text, [turn.user_text for turn in self._recent_turns], token, pending=pending)
            token.check()
            return result
        except DialogueCancelled:
            raise
        except Exception:
            return MemoryIntent()

    def interpret_confirmation(self, memory_id, text, token):
        candidate = self._pending.get(memory_id)
        if candidate is None or self.session_status().state.value != "awaiting_confirmation":
            return MemoryIntent()
        token.check()
        simple = parse_memory_confirmation(text)
        if simple is not None:
            return MemoryIntent("approve" if simple else "reject")
        intent = self._interpret_memory(text, token, pending=candidate.content)
        if intent.intent == "revise":
            proposal = explicit_memory_request("请记住，" + intent.content)
            if proposal is None or proposal.memory_candidate is None:
                return MemoryIntent()
            token.check()
            revised = replace(proposal.memory_candidate, id=memory_id)
            self._pending.save(revised)
            return MemoryIntent("revise", revised.content)
        return intent if intent.intent in {"approve", "reject"} else MemoryIntent()

    def list_memories(self) -> tuple[ConfirmedMemory, ...]:
        return self._memories.list_all()

    def delete_memory(self, memory_id: str) -> bool:
        deleted = self._memories.delete(memory_id)
        if deleted:
            self.clear_history()
        return deleted

    def clear_history(self) -> None:
        self._recent_turns.clear()

    def growth_state(self) -> GrowthState:
        return self._growth_repository.get()

    def dialogue_status(self) -> DialogueEngineStatus:
        status_method = getattr(self._dialogue, "status", None)
        if callable(status_method):
            status = status_method()
            if isinstance(status, DialogueEngineStatus):
                return status
        return DialogueEngineStatus(
            mode="custom",
            active_provider="custom",
            model=None,
            configured=True,
        )

    def reset_state(self) -> None:
        self.clear_history()
        self._pending.clear()
        self._memories.clear()
        self._growth_repository.reset()
        self._session.dispatch(EventType.INTERRUPT)

    def session_status(self) -> SessionSnapshot:
        return self._session.snapshot()

    def event_history(self) -> tuple[RobotEvent, ...]:
        return self._session.event_history()

    def set_muted(self, muted: bool) -> SessionSnapshot:
        self._session.dispatch(EventType.MUTE_CHANGED, {"muted": muted})
        return self._session.snapshot()

    def set_online(self, online: bool) -> SessionSnapshot:
        self._session.dispatch(EventType.NETWORK_CHANGED, {"online": online})
        return self._session.snapshot()

    def set_battery(self, percent: int) -> SessionSnapshot:
        bounded = max(0, min(int(percent), 100))
        event_type = (
            EventType.LOW_BATTERY
            if bounded <= 20
            else EventType.BATTERY_CHANGED
        )
        self._session.dispatch(event_type, {"percent": bounded})
        return self._session.snapshot()

    def interrupt(self) -> SessionSnapshot:
        if self._active_cancellation is not None:
            self._active_cancellation.cancel()
        self._session.dispatch(EventType.INTERRUPT)
        return self._session.snapshot()

    def touch(self) -> None:
        self._session.dispatch(EventType.TOUCH)
        action, _ = self._safety.approve_action(
            ActionCommand(ActionName.NOD, 0.3)
        )
        self._actuator.present(
            "感觉到了，摸摸头很舒服。",
            Emotion.HAPPY,
            action,
        )

    def collision(self) -> SessionSnapshot:
        self._session.dispatch(EventType.COLLISION)
        return self._session.snapshot()

    def shutdown(self) -> None:
        if self._active_cancellation is not None:
            self._active_cancellation.cancel()
        self.clear_history()
        self._session.dispatch(EventType.SHUTDOWN)

