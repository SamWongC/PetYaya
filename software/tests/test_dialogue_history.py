import json
import unittest
from unittest.mock import Mock

from test_orchestrator import build_test_subject
from pet_yaya.adapters.openai_dialogue import LMStudioChatDialogueEngine, OpenAIResponsesDialogueEngine
from pet_yaya.domain.models import DialogueContext, DialogueResult, DialogueTurn


class HistoryTests(unittest.TestCase):
    def test_history_is_ordered_bounded_and_not_long_term_memory(self):
        subject, _, memories = build_test_subject()
        model = Mock()
        model.respond.return_value = DialogueResult(speech="解释内容")
        subject._dialogue = model
        for i in range(6):
            subject.interact(str(i))
        history = model.respond.call_args.args[1].recent_turns
        self.assertEqual([t.user_text for t in history], ["1", "2", "3", "4"])
        self.assertTrue(all(t.assistant_text == "解释内容" for t in history))
        self.assertEqual(memories.list_all(), ())

    def test_clear_and_new_instance_have_no_history(self):
        subject, _, _ = build_test_subject()
        subject.interact("你好")
        growth = subject.growth_state().interaction_count
        subject.clear_history()
        model = Mock()
        model.respond.return_value = DialogueResult(speech="好")
        subject._dialogue = model
        subject.interact("继续")
        self.assertEqual(model.respond.call_args.args[1].recent_turns, ())
        self.assertEqual(subject.growth_state().interaction_count, growth + 1)
        other, _, _ = build_test_subject()
        other._dialogue = model
        other.interact("继续")
        self.assertEqual(model.respond.call_args.args[1].recent_turns, ())

    def test_rejected_candidate_and_failed_response_are_not_in_history(self):
        subject, _, _ = build_test_subject()
        result = subject.interact("请记住，我的名字是小林")
        subject.confirm_memory(result.pending_memory_id, False)
        model = Mock()
        model.respond.side_effect = RuntimeError("failure")
        subject._dialogue = model
        with self.assertRaises(RuntimeError):
            subject.interact("失败输入")
        subject.interrupt()
        model.respond.side_effect = None
        model.respond.return_value = DialogueResult(speech="好")
        subject.interact("继续")
        self.assertEqual(model.respond.call_args.args[1].recent_turns, ())

    def test_delete_reset_and_shutdown_clear_history(self):
        for operation in ("delete", "reset", "shutdown"):
            with self.subTest(operation=operation):
                subject, _, _ = build_test_subject()
                result = subject.interact("请记住，我喜欢恐龙")
                subject.confirm_memory(result.pending_memory_id, True)
                subject.interact("你好")
                if operation == "delete":
                    subject.delete_memory(subject.list_memories()[0].id)
                elif operation == "reset":
                    subject.reset_state()
                else:
                    subject.shutdown()
                self.assertEqual(tuple(subject._recent_turns), ())

    def test_both_adapters_send_same_bounded_history(self):
        ctx = DialogueContext((), 0, (), tuple(DialogueTurn(str(i) * 900, "答" * 500) for i in range(6)))
        cloud = OpenAIResponsesDialogueEngine(api_key="test")
        local = LMStudioChatDialogueEngine(api_key="test")
        a = json.loads(cloud._build_payload("更学术一点", ctx)["input"])
        messages = local._build_chat_payload("更学术一点", ctx)["messages"]
        b = json.loads(messages[1]["content"])
        turns = a.pop("recent_turns")
        self.assertEqual(a, b)
        self.assertEqual(len(turns), 4)
        self.assertEqual(messages[2], {"role": "user", "content": "2" * 800})
        self.assertEqual(messages[3], {"role": "assistant", "content": "答" * 400})
        self.assertEqual(messages[-1], {"role": "user", "content": "更学术一点"})
        self.assertEqual([m["role"] for m in messages[2:-1]], ["user", "assistant"] * 4)

