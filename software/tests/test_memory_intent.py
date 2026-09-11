import json
import unittest
import io
from contextlib import redirect_stdout
from unittest.mock import Mock, patch
from pet_yaya.main import main
from test_orchestrator import build_test_subject
from pet_yaya.adapters.memory_intent import LocalMemoryInterpreter
from pet_yaya.domain.memory_intent import MemoryIntent
from pet_yaya.domain.models import DialogueTurn
from pet_yaya.config import DialogueSettings
from pet_yaya.domain.cancellation import CancellationToken, DialogueCancelled


class IntentTests(unittest.TestCase):
    def test_voice_revision_is_read_back_before_second_consent(self):
        subject, _, _ = build_test_subject()
        subject._memory_interpreter = Mock()
        subject._memory_interpreter.interpret.return_value = MemoryIntent("revise", "我喜欢三角龙")
        voice = Mock(enabled=True)
        voice.listen.side_effect = ["请记住我喜欢恐龙", "可以，不过我喜欢三角龙", "可以啊"]
        with patch("pet_yaya.main.build_simulator", return_value=subject), patch("builtins.input", side_effect=["/listen", "/quit"]), redirect_stdout(io.StringIO()):
            main(voice)
        self.assertIn("三角龙", voice.speak.call_args_list[1].args[0])
        self.assertEqual(subject.list_memories()[0].content, "我喜欢三角龙")
        self.assertEqual(voice.listen.call_count, 3)

    def test_typed_natural_confirmation(self):
        subject, _, _ = build_test_subject()
        with patch("pet_yaya.main.build_simulator", return_value=subject), patch("builtins.input", side_effect=["以后别忘了，我喜欢恐龙", "可以啊", "/quit"]), redirect_stdout(io.StringIO()):
            main()
        self.assertEqual(len(subject.list_memories()), 1)

    def test_natural_request_rules(self):
        for text in ("以后别忘了，我喜欢恐龙", "帮我记下来，我喜欢恐龙", "下次聊天你要记得我叫小林"):
            subject, _, _ = build_test_subject()
            result = subject.interact(text)
            self.assertIsNotNone(result.pending_memory_id)
            self.assertEqual(subject.list_memories(), ())

    def test_natural_approval_only_with_live_candidate(self):
        for text in ("可以啊", "好呀", "没问题"):
            subject, _, _ = build_test_subject()
            token = CancellationToken()
            self.assertEqual(subject.interpret_confirmation("missing", text, token).intent, "uncertain")
            result = subject.interact("请记住我喜欢恐龙")
            decision = subject.interpret_confirmation(result.pending_memory_id, text, token)
            self.assertEqual(decision.intent, "approve")
            self.assertEqual(subject.list_memories(), ())

    def test_revision_requires_new_approval_and_no_extra_growth(self):
        subject, _, _ = build_test_subject()
        subject._memory_interpreter = Mock()
        subject._memory_interpreter.interpret.return_value = MemoryIntent("revise", "我喜欢三角龙")
        result = subject.interact("请记住我喜欢恐龙")
        revised = subject.interpret_confirmation(result.pending_memory_id, "可以，不过我喜欢三角龙", CancellationToken())
        self.assertEqual(revised.intent, "revise")
        self.assertEqual(subject.list_memories(), ())
        decision = subject.interpret_confirmation(result.pending_memory_id, "可以啊", CancellationToken())
        subject.confirm_memory(result.pending_memory_id, decision.intent == "approve")
        self.assertEqual(subject.list_memories()[0].content, "我喜欢三角龙")
        self.assertEqual(subject.growth_state().interaction_count, 1)

    def test_sensitive_revision_blocked(self):
        subject, _, _ = build_test_subject()
        subject._memory_interpreter = Mock()
        subject._memory_interpreter.interpret.return_value = MemoryIntent("revise", "我的密码是abc")
        result = subject.interact("请记住我喜欢恐龙")
        decision = subject.interpret_confirmation(result.pending_memory_id, "改成我的密码是abc", CancellationToken())
        self.assertEqual(decision.intent, "uncertain")
        self.assertEqual(subject._pending.get(result.pending_memory_id).content, "我喜欢恐龙")

    def classify(self, kind, content="", text="我喜欢恐龙", history=None, pending=None):
        transport = Mock()
        def events(*args):
            yield {"choices": [{"delta": {"content": json.dumps({"intent": kind, "content": content})}, "finish_reason": None}]}
            yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}
        transport.stream_json.side_effect = events
        return LocalMemoryInterpreter(DialogueSettings(mode="local"), transport).interpret(text, history or [], CancellationToken(), pending=pending)

    def test_semantic_extraction_requires_user_evidence(self):
        self.assertEqual(self.classify("request", "我喜欢恐龙", "把这个记下来", ["我喜欢恐龙"]).intent, "request")
        self.assertEqual(self.classify("request", "我喜欢猫").intent, "uncertain")

    def test_semantic_approval_negation_question_condition_blocked(self):
        for text in ("可以吗？", "可以，不过不是恐龙", "我不确定", "随便吧"):
            self.assertEqual(self.classify("approve", text=text, pending="我喜欢恐龙").intent, "uncertain")

    def test_semantic_revision_cannot_take_old_history(self):
        self.assertEqual(self.classify("revise", "我喜欢猫", "改一下", ["我喜欢猫"], "我喜欢恐龙").intent, "uncertain")

    def test_interpreter_failure_does_not_authorize(self):
        subject, _, _ = build_test_subject()
        subject._memory_interpreter = Mock()
        subject._memory_interpreter.interpret.side_effect = RuntimeError("offline")
        result = subject.interact("请记住我喜欢恐龙")
        self.assertEqual(subject.interpret_confirmation(result.pending_memory_id, "大概可以吧", CancellationToken()).intent, "uncertain")

    def test_cancelled_semantics_never_commit(self):
        subject, _, _ = build_test_subject()
        subject._memory_interpreter = Mock()
        subject._memory_interpreter.interpret.side_effect = DialogueCancelled()
        result = subject.interact("请记住我喜欢恐龙")
        with self.assertRaises(DialogueCancelled):
            subject.interpret_confirmation(result.pending_memory_id, "我认为可以记下这件事情", CancellationToken())
        self.assertEqual(subject.list_memories(), ())

