from __future__ import annotations

from collections.abc import Callable

from pet_yaya.domain.models import (
    ActionCommand,
    ActionName,
    DialogueContext,
    DialogueResult,
    Emotion,
    MemoryCandidate,
)
from pet_yaya.domain.session import SessionSnapshot


class RuleBasedDialogueEngine:
    """Offline placeholder used to validate application flows."""

    def respond(self, text: str, context: DialogueContext) -> DialogueResult:
        if text.startswith("我喜欢"):
            preference = text.removeprefix("我喜欢").strip(" ，。！!")
            if preference:
                return DialogueResult(
                    speech=f"原来你喜欢{preference}呀。",
                    emotion=Emotion.CURIOUS,
                    action=ActionCommand(ActionName.TILT_HEAD),
                    memory_candidate=MemoryCandidate(
                        category="preference",
                        content=f"主人喜欢{preference}",
                    ),
                )

        if text.startswith("记住"):
            fact = text.removeprefix("记住").strip(" ：:，。！!")
            if fact:
                return DialogueResult(
                    speech=f"我听到的是：{fact}。",
                    emotion=Emotion.CALM,
                    action=ActionCommand(ActionName.NOD),
                    memory_candidate=MemoryCandidate(
                        category="user_taught",
                        content=fact,
                    ),
                )

        if "你好" in text or "嗨" in text:
            return DialogueResult(
                speech="你好！今天想和我一起做什么？",
                emotion=Emotion.HAPPY,
                action=ActionCommand(ActionName.HAPPY_WIGGLE, 0.4),
            )

        if "困" in text or "晚安" in text:
            return DialogueResult(
                speech="那我们都慢下来吧。晚安，做个好梦。",
                emotion=Emotion.SLEEPY,
                action=ActionCommand(ActionName.SLEEP_POSE, 0.3),
            )

        memory_hint = ""
        if context.memories:
            memory_hint = f" 我已经记住了{len(context.memories)}件你确认过的事情。"
        return DialogueResult(
            speech=f"我听见了：{text}。{memory_hint}".strip(),
            emotion=Emotion.CURIOUS,
            action=ActionCommand(ActionName.TILT_HEAD, 0.3),
        )


class ConservativeSafetyPolicy:
    _ALLOWED_ACTIONS = frozenset(action.value for action in ActionName)

    def approve_action(self, action: ActionCommand) -> tuple[ActionCommand, bool]:
        if action.name not in self._ALLOWED_ACTIONS:
            return ActionCommand(ActionName.IDLE, 0.0), True
        safe_intensity = max(0.0, min(float(action.intensity), 1.0))
        adjusted = safe_intensity != action.intensity
        return ActionCommand(action.name, safe_intensity), adjusted


class VirtualDeviceSafetyPolicy:
    """Adds virtual device constraints to the base action whitelist."""

    def __init__(
        self,
        base_policy: ConservativeSafetyPolicy,
        status_provider: Callable[[], SessionSnapshot],
    ) -> None:
        self._base_policy = base_policy
        self._status_provider = status_provider

    def approve_action(self, action: ActionCommand) -> tuple[ActionCommand, bool]:
        safe_action, adjusted = self._base_policy.approve_action(action)
        status = self._status_provider()
        if (
            status.battery_percent <= 20
            and safe_action.name != ActionName.IDLE
        ):
            return ActionCommand(ActionName.IDLE, 0.0), True
        return safe_action, adjusted


class ConsoleActuator:
    def __init__(self) -> None:
        self._preview = ""

    def preview(self, chunk: str) -> None:
        if not self._preview:
            print("\nYaya：", end="", flush=True)
        print(chunk, end="", flush=True)
        self._preview += chunk

    def abort_preview(self) -> None:
        if self._preview:
            print("\n      [以上为未完成回复，未计入短期历史或成长]")
        self._preview = ""

    def present(
        self, speech: str, emotion: Emotion, action: ActionCommand
    ) -> None:
        if self._preview and speech.startswith(self._preview.rstrip()):
            print(speech[len(self._preview.rstrip()):])
        else:
            print(f"\nYaya：{speech}")
        self._preview = ""
        print(
            f"      [表情={emotion.value} 动作={action.name}"
            f" 强度={action.intensity:.1f}]"
        )

