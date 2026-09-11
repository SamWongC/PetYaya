import io
import json
import threading
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from test_orchestrator import build_test_subject
from pet_yaya.adapters.openai_dialogue import (
    DialogueServiceError, LMStudioChatDialogueEngine, ResilientDialogueEngine,
)
from pet_yaya.adapters.simulator import ConsoleActuator, RuleBasedDialogueEngine
from pet_yaya.adapters.streaming import speech_prefix, stream_chat_events
from pet_yaya.domain.cancellation import CancellationToken, DialogueCancelled
from pet_yaya.domain.models import ActionName, DialogueContext, DialogueTurn
from pet_yaya.domain.session import SessionState


def result_json(speech="你好，今天一起看星星吧！", action="nod", memory=None):
    return json.dumps({"speech": speech, "emotion": "happy", "action": {
        "name": action, "intensity": 0.3}, "memory": memory}, ensure_ascii=False)


def fragments(document, reason="stop"):
    for i in range(0, len(document), 3):
        yield {"choices": [{"delta": {"content": document[i:i + 3]}, "finish_reason": None}]}
    yield {"choices": [{"delta": {}, "finish_reason": reason}]}


class StreamTransport:
    def __init__(self, plans):
        self.plans = iter(plans)
        self.closed = 0
        self.calls = 0

    def stream_json(self, url, headers, payload, timeout_seconds, cancellation):
        self.calls += 1
        self.payload = payload
        try:
            yield from next(self.plans)
        finally:
            self.closed += 1


def build_stream_subject(plans):
    transport = StreamTransport(plans)
    primary = LMStudioChatDialogueEngine(api_key="test", transport=transport)
    router = ResilientDialogueEngine(RuleBasedDialogueEngine(), "local", "test", "local", primary)
    subject, actuator, memories = build_test_subject()
    subject._dialogue = router
    return subject, actuator, memories, transport


class StreamingTests(unittest.TestCase):
    def test_invalid_intensity_keeps_complete_speech_and_commits_once(self):
        for intensity in (-1, 8, None, "strong", True, [], {},
                          float("nan"), float("inf"), -float("inf"), 10 ** 400):
            with self.subTest(intensity=intensity):
                document = json.loads(result_json())
                document["action"]["intensity"] = intensity
                subject, actuator, memories, _ = build_stream_subject([
                    fragments(json.dumps(document, ensure_ascii=False))])
                chunks = []
                result = subject.interact("讲个故事", on_text=chunks.append)
                self.assertEqual(result.speech, document["speech"])
                self.assertEqual("".join(chunks), result.speech)
                self.assertEqual(result.action.name, ActionName.IDLE)
                self.assertEqual(result.action.intensity, 0.0)
                self.assertTrue(result.safety_adjusted)
                self.assertEqual(len(actuator.calls), 1)
                self.assertEqual(subject.growth_state().interaction_count, 1)
                self.assertEqual(len(subject._recent_turns), 1)
                self.assertEqual(subject.session_status().state, SessionState.IDLE)
                self.assertEqual(memories.list_all(), ())

    def test_valid_intensity_is_preserved(self):
        for intensity in (0, 0.3, 1, "0.5"):
            with self.subTest(intensity=intensity):
                document = json.loads(result_json())
                document["action"]["intensity"] = intensity
                result = LMStudioChatDialogueEngine._parse_result(json.dumps(document))
                self.assertEqual(result.action.name, ActionName.NOD)
                self.assertEqual(result.action.intensity, float(intensity))
                self.assertFalse(result.action_adjusted)

    def test_intensity_fallback_does_not_bypass_memory_validation(self):
        document = json.loads(result_json(memory={"category": "unknown", "content": "测试"}))
        document["action"].pop("intensity")
        subject, actuator, memories, _ = build_stream_subject([
            fragments(json.dumps(document))])
        with self.assertRaises(DialogueServiceError):
            subject.interact("你好", on_text=lambda s: None)
        self.assertEqual(actuator.calls, [])
        self.assertEqual(subject.growth_state().interaction_count, 0)
        self.assertEqual(memories.list_all(), ())

    def test_intensity_fallback_keeps_memory_pending_until_confirmation(self):
        document = json.loads(result_json(memory={"category": "preference", "content": "用户喜欢恐龙"}))
        document["action"].pop("intensity")
        subject, _, memories, _ = build_stream_subject([fragments(json.dumps(document))])
        result = subject.interact("我喜欢恐龙", on_text=lambda s: None)
        self.assertTrue(result.safety_adjusted)
        self.assertIsNotNone(result.pending_memory_id)
        self.assertEqual(memories.list_all(), ())
        subject.confirm_memory(result.pending_memory_id, True)
        self.assertEqual(len(memories.list_all()), 1)

    def test_cli_ctrl_c_sets_cancellation_and_restores_handler(self):
        import signal
        from pet_yaya.main import cancel_on_ctrl_c
        previous = signal.getsignal(signal.SIGINT)
        token = CancellationToken()
        with cancel_on_ctrl_c(token):
            signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
            with self.assertRaises(DialogueCancelled):
                token.check()
        self.assertIs(signal.getsignal(signal.SIGINT), previous)

    def test_partial_json_unicode_escapes_and_top_level_only(self):
        value = '你好"呀\\\n😀'
        document = json.dumps({"memory": {"speech": "不要显示"}, "speech": value})
        previous = ""
        for i in range(len(document) + 1):
            prefix = speech_prefix(document[:i])
            self.assertTrue(prefix.startswith(previous))
            self.assertTrue(value.startswith(prefix))
            prefix.encode("utf-8")
            previous = prefix
        self.assertEqual(previous, value)

    def test_success_previews_before_actions_and_commits_once(self):
        subject, actuator, memories, transport = build_stream_subject([fragments(result_json())])
        chunks = []
        def preview(chunk):
            self.assertEqual(actuator.calls, [])
            self.assertEqual(subject.growth_state().interaction_count, 0)
            self.assertEqual(subject.session_status().state, SessionState.SPEAKING)
            chunks.append(chunk)
        result = subject.interact("讲个故事", on_text=preview)
        self.assertEqual("".join(chunks), result.speech)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(len(actuator.calls), 1)
        self.assertEqual(subject.growth_state().interaction_count, 1)
        self.assertEqual(subject.session_status().state, SessionState.IDLE)
        self.assertEqual(memories.list_all(), ())
        self.assertEqual(transport.closed, 1)

    def test_cancel_after_partial_has_no_effects_and_next_turn_works(self):
        subject, actuator, memories, transport = build_stream_subject([
            fragments(result_json()), fragments(result_json("恢复了"))])
        token = CancellationToken()
        def preview(chunk):
            token.cancel()
        with self.assertRaises(DialogueCancelled):
            subject.interact("讲个故事", on_text=preview, cancellation=token)
        self.assertEqual(transport.closed, 1)
        self.assertEqual(actuator.calls, [])
        self.assertEqual(memories.list_all(), ())
        self.assertEqual(tuple(subject._recent_turns), ())
        self.assertEqual(subject.growth_state().interaction_count, 0)
        self.assertEqual(subject.session_status().state, SessionState.IDLE)
        self.assertEqual(subject.interact("你好", on_text=lambda s: None).speech, "恢复了")

    def test_keyboard_interrupt_and_pre_cancel_do_not_start_fallback(self):
        subject, actuator, _, transport = build_stream_subject([fragments(result_json())])
        def preview(chunk):
            raise KeyboardInterrupt
        with self.assertRaises(DialogueCancelled):
            subject.interact("你好", on_text=preview)
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(DialogueCancelled):
            subject.interact("你好", on_text=preview, cancellation=token)
        self.assertEqual(actuator.calls, [])
        self.assertEqual(transport.calls, 1)

    def test_incomplete_and_invalid_final_do_not_commit_partial(self):
        plans = [fragments(result_json(), "length"),
                 fragments(result_json(action="drive_full_speed")),
                 iter(list(fragments(result_json()))[:-1])]
        for plan in plans:
            with self.subTest(plan=plan):
                subject, actuator, memories, _ = build_stream_subject([plan])
                with self.assertRaises(DialogueServiceError):
                    subject.interact("你好", on_text=lambda s: None)
                self.assertEqual(actuator.calls, [])
                self.assertEqual(subject.growth_state().interaction_count, 0)
                self.assertEqual(memories.list_all(), ())
                self.assertEqual(tuple(subject._recent_turns), ())

    def test_failure_before_preview_can_fallback(self):
        def failed():
            raise DialogueServiceError("offline")
            yield
        subject, actuator, _, _ = build_stream_subject([failed()])
        result = subject.interact("你好", on_text=lambda s: None)
        self.assertIn("你好", result.speech)
        self.assertEqual(subject.dialogue_status().active_provider, "rules")
        self.assertEqual(len(actuator.calls), 1)

    def test_stream_memory_still_needs_confirmation(self):
        document = result_json(memory={"category": "preference", "content": "用户喜欢恐龙"})
        subject, _, memories, _ = build_stream_subject([fragments(document)])
        result = subject.interact("我喜欢恐龙", on_text=lambda s: None)
        self.assertEqual(memories.list_all(), ())
        self.assertIsNotNone(result.pending_memory_id)
        self.assertIn("我可以记住", result.speech)
        subject.confirm_memory(result.pending_memory_id, True)
        self.assertEqual(len(memories.list_all()), 1)

    def test_rewrite_is_buffered_and_retried(self):
        transport = StreamTransport([fragments(result_json("原文")), fragments(result_json("简单版本"))])
        engine = LMStudioChatDialogueEngine(api_key="test", transport=transport)
        chunks = []
        result = engine.respond_stream("更简单一点", DialogueContext((), 0, (), (DialogueTurn("问题", "原文"),)), chunks.append, CancellationToken())
        self.assertEqual(chunks, [])
        self.assertEqual(result.speech, "简单版本")
        self.assertEqual(transport.calls, 2)

    def test_console_does_not_duplicate_speech_and_clears_on_abort(self):
        console = ConsoleActuator()
        subject, _, _, _ = build_stream_subject([fragments(result_json())])
        subject._actuator = console
        output = io.StringIO()
        with redirect_stdout(output):
            result = subject.interact("你好", on_text=console.preview)
        self.assertEqual(output.getvalue().count(result.speech), 1)
        with redirect_stdout(output):
            console.preview("半截")
            console.abort_preview()
        self.assertEqual(console._preview, "")


class FakeResponse(io.BytesIO):
    status = 200
    def getheader(self, name, default=""):
        return "text/event-stream"


class SSETransportTests(unittest.TestCase):
    def connection(self, response):
        from unittest.mock import Mock
        connection = Mock()
        connection.getresponse.return_value = response
        return connection

    def test_sse_multiline_and_comments(self):
        response = FakeResponse(b': ping\r\ndata: {"choices":\r\ndata: []}\r\n\r\ndata: [DONE]\r\n\r\n')
        connection = self.connection(response)
        with patch("pet_yaya.adapters.streaming.http.client.HTTPConnection", return_value=connection):
            events = list(stream_chat_events("http://localhost:1234/v1/chat/completions", {}, {}, 1, CancellationToken()))
        self.assertEqual(events, [{"choices": []}])
        connection.sock.shutdown.assert_called()

    def test_missing_done_and_bad_json_are_errors(self):
        for raw in (b'data: {}\n\n', b'data: not-json\n\n'):
            connection = self.connection(FakeResponse(raw))
            with patch("pet_yaya.adapters.streaming.http.client.HTTPConnection", return_value=connection):
                with self.assertRaises(DialogueServiceError):
                    list(stream_chat_events("http://localhost:1234/", {}, {}, 1, CancellationToken()))

    def test_cancel_while_server_silent_closes_socket(self):
        waiting = threading.Event()
        released = threading.Event()
        token = CancellationToken()
        class SilentResponse(FakeResponse):
            def readline(self, size=-1):
                waiting.set()
                released.wait(2)
                return b""
        connection = self.connection(SilentResponse())
        connection.sock.shutdown.side_effect = lambda how: released.set()
        def cancel():
            waiting.wait(1)
            token.cancel()
        helper = threading.Thread(target=cancel)
        helper.start()
        with patch("pet_yaya.adapters.streaming.http.client.HTTPConnection", return_value=connection):
            with self.assertRaises(DialogueCancelled):
                list(stream_chat_events("http://localhost:1234/", {}, {}, 2, token))
        helper.join(1)
        self.assertTrue(released.is_set())

