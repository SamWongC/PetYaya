from __future__ import annotations

import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from pet_yaya.adapters.openai_dialogue import (  # noqa: E402
    DialogueServiceError,
    LMStudioChatDialogueEngine,
    OpenAIResponsesDialogueEngine,
    ResilientDialogueEngine,
    UrllibJsonTransport,
)
from pet_yaya.adapters.simulator import RuleBasedDialogueEngine  # noqa: E402
from pet_yaya.config import DialogueSettings  # noqa: E402
from pet_yaya.domain.models import (  # noqa: E402
    ActionName,
    DialogueContext,
    Emotion,
    ConfirmedMemory,
    MemoryCandidate,
)


def context() -> DialogueContext:
    return DialogueContext(
        memories=(),
        interaction_count=2,
        unlocked_skills=("curious_greeting",),
    )


class FakeTransport:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[
            tuple[str, dict[str, str], dict[str, object], float]
        ] = []

    def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> dict[str, object]:
        self.calls.append((url, headers, payload, timeout_seconds))
        return self.response


class FailingTransport:
    def __init__(self) -> None:
        self.call_count = 0

    def post_json(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> dict[str, object]:
        self.call_count += 1
        raise DialogueServiceError("simulated timeout")


def api_response(result: dict[str, object]) -> dict[str, object]:
    return {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(result, ensure_ascii=False),
                    }
                ],
            }
        ]
    }


def chat_api_response(result: dict[str, object]) -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps(result, ensure_ascii=False),
                }
            }
        ]
    }


class OpenAIDialogueTests(unittest.TestCase):
    def test_memory_perspective_preserves_original_and_summary(self) -> None:
        memories = tuple(
            ConfirmedMemory.from_candidate(MemoryCandidate(
                category="profile", content=content, source=source
            ))
            for content, source in (
                ("我的名字是小明", "explicit_user_request"),
                ("我是你的开发者", "user_statement"),
                ("用户喜欢恐龙", "model_suggestion"),
            )
        )
        ctx = DialogueContext(memories, 2, ())
        cloud = OpenAIResponsesDialogueEngine(api_key="test")
        local = LMStudioChatDialogueEngine(api_key="test")
        cloud_context = json.loads(cloud._build_payload("我是谁", ctx)["input"])
        local_context = json.loads(local._build_chat_payload("我是谁", ctx)["messages"][1]["content"])
        cloud_context.pop("recent_turns")
        self.assertEqual(cloud_context, local_context)
        items = local_context["confirmed_memories"]
        self.assertEqual([m["content"] for m in items], [m.content for m in memories])
        self.assertEqual([m["perspective"] for m in items], ["user_to_yaya", "user_to_yaya", "summary"])
        self.assertEqual(local_context["user_text"], "我是谁")

    def test_structured_response_maps_to_domain_result(self) -> None:
        transport = FakeTransport(
            api_response(
                {
                    "speech": "你好呀，今天想做什么？",
                    "emotion": "happy",
                    "action": {
                        "name": "happy_wiggle",
                        "intensity": 0.4,
                    },
                    "memory": None,
                }
            )
        )
        engine = OpenAIResponsesDialogueEngine(
            api_key="test-key", transport=transport
        )

        result = engine.respond("你好", context())

        self.assertEqual(result.emotion, Emotion.HAPPY)
        self.assertEqual(result.action.name, ActionName.HAPPY_WIGGLE)
        self.assertIsNone(result.memory_candidate)

    def test_request_disables_storage_and_uses_strict_schema(self) -> None:
        transport = FakeTransport(
            api_response(
                {
                    "speech": "听到了。",
                    "emotion": "calm",
                    "action": {"name": "nod", "intensity": 0.2},
                    "memory": None,
                }
            )
        )
        engine = OpenAIResponsesDialogueEngine(
            api_key="test-key",
            safety_identifier="local-pseudonym",
            transport=transport,
        )

        engine.respond("测试", context())

        _, headers, payload, _ = transport.calls[0]
        text_config = payload["text"]
        self.assertIsInstance(text_config, dict)
        response_format = text_config["format"]
        self.assertFalse(payload["store"])
        self.assertEqual(payload["model"], "gpt-5.6")
        self.assertTrue(response_format["strict"])
        self.assertEqual(response_format["type"], "json_schema")
        self.assertEqual(
            payload["safety_identifier"], "local-pseudonym"
        )
        self.assertEqual(headers["Authorization"], "Bearer test-key")

    def test_model_memory_is_only_a_pending_candidate(self) -> None:
        transport = FakeTransport(
            api_response(
                {
                    "speech": "原来你喜欢天文呀。",
                    "emotion": "curious",
                    "action": {"name": "tilt_head", "intensity": 0.3},
                    "memory": {
                        "category": "preference",
                        "content": "主人喜欢天文",
                    },
                }
            )
        )
        engine = OpenAIResponsesDialogueEngine(
            api_key="test-key", transport=transport
        )

        result = engine.respond("我很喜欢天文", context())

        self.assertIsNotNone(result.memory_candidate)
        self.assertEqual(
            result.memory_candidate.content, "主人喜欢天文"
        )
        self.assertEqual(
            result.memory_candidate.source, "model_suggestion"
        )

    def test_invalid_model_action_is_rejected(self) -> None:
        transport = FakeTransport(
            api_response(
                {
                    "speech": "出发。",
                    "emotion": "happy",
                    "action": {
                        "name": "drive_at_full_speed",
                        "intensity": 1,
                    },
                    "memory": None,
                }
            )
        )
        engine = OpenAIResponsesDialogueEngine(
            api_key="test-key", transport=transport
        )

        with self.assertRaises(DialogueServiceError):
            engine.respond("全速前进", context())

    def test_service_failure_falls_back_to_rules(self) -> None:
        failing_transport = FailingTransport()
        primary = OpenAIResponsesDialogueEngine(
            api_key="test-key", transport=failing_transport
        )
        router = ResilientDialogueEngine(
            fallback=RuleBasedDialogueEngine(),
            primary=primary,
            mode="auto",
            model="gpt-5.6",
        )

        result = router.respond("你好", context())

        self.assertIn("你好", result.speech)
        self.assertEqual(router.status().active_provider, "rules")
        self.assertIn("timeout", router.status().last_error or "")

    def test_offline_mode_skips_external_request(self) -> None:
        failing_transport = FailingTransport()
        primary = OpenAIResponsesDialogueEngine(
            api_key="test-key", transport=failing_transport
        )
        router = ResilientDialogueEngine(
            fallback=RuleBasedDialogueEngine(),
            primary=primary,
            mode="auto",
            model="gpt-5.6",
            online_provider=lambda: False,
        )

        result = router.respond("你好", context())

        self.assertIn("你好", result.speech)
        self.assertEqual(failing_transport.call_count, 0)
        self.assertIn("离线", router.status().last_error or "")

    def test_environment_configuration_is_bounded(self) -> None:
        settings = DialogueSettings.from_env(
            {
                "PET_YAYA_DIALOGUE_MODE": "openai",
                "OPENAI_API_KEY": "secret",
                "PET_YAYA_OPENAI_MODEL": "example-model",
                "PET_YAYA_OPENAI_TIMEOUT_SECONDS": "999",
            }
        )

        self.assertEqual(settings.mode, "openai")
        self.assertEqual(settings.api_key, "secret")
        self.assertEqual(settings.model, "example-model")
        self.assertEqual(settings.timeout_seconds, 120.0)

    def test_local_environment_configuration(self) -> None:
        settings = DialogueSettings.from_env(
            {
                "PET_YAYA_DIALOGUE_MODE": "local",
                "PET_YAYA_LOCAL_MODEL": "qwen/custom",
                "PET_YAYA_LOCAL_BASE_URL": "http://localhost:1234/v1/",
                "PET_YAYA_LOCAL_API_TOKEN": "local-token",
            }
        )

        self.assertEqual(settings.mode, "local")
        self.assertEqual(settings.local_model, "qwen/custom")
        self.assertEqual(
            settings.local_base_url, "http://localhost:1234/v1"
        )
        self.assertEqual(settings.local_api_token, "local-token")

    def test_local_provider_is_reported_after_success(self) -> None:
        transport = FakeTransport(
            chat_api_response(
                {
                    "speech": "本地模型已经准备好了。",
                    "emotion": "happy",
                    "action": {"name": "nod", "intensity": 0.2},
                    "memory": None,
                }
            )
        )
        primary = LMStudioChatDialogueEngine(
            api_key="local-token",
            model="qwen/qwen3.5-9b",
            transport=transport,
        )
        router = ResilientDialogueEngine(
            fallback=RuleBasedDialogueEngine(),
            primary=primary,
            mode="local",
            model="qwen/qwen3.5-9b",
            primary_provider="local",
            online_provider=lambda: False,
        )

        result = router.respond("你好", context())

        self.assertIn("准备好了", result.speech)
        self.assertEqual(router.status().active_provider, "local")
        url, _, payload, _ = transport.calls[0]
        self.assertTrue(url.endswith("/chat/completions"))
        response_format = payload["response_format"]
        self.assertIsInstance(response_format, dict)
        self.assertEqual(response_format["type"], "json_schema")

    def test_http_error_detail_exposes_safe_service_message(self) -> None:
        body = io.BytesIO(
            json.dumps(
                {
                    "error": {
                        "message": "model is not loaded",
                        "code": "model_not_found",
                        "param": "model",
                    }
                }
            ).encode("utf-8")
        )
        error = urllib.error.HTTPError(
            "http://127.0.0.1:1234/v1/responses",
            400,
            "Bad Request",
            {},
            body,
        )

        detail = UrllibJsonTransport._http_error_detail(error)

        self.assertIn("model is not loaded", detail)
        self.assertIn("model_not_found", detail)
        self.assertIn("param=model", detail)


if __name__ == "__main__":
    unittest.main()

