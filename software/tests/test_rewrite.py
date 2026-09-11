import unittest
from unittest.mock import Mock

from test_openai_dialogue import chat_api_response
from pet_yaya.adapters.openai_dialogue import LMStudioChatDialogueEngine
from pet_yaya.domain.models import DialogueContext, DialogueTurn


def response(speech):
    return chat_api_response({"speech": speech, "emotion": "happy", "action": {"name": "nod", "intensity": 0.3}, "memory": None})


class RewriteTests(unittest.TestCase):
    def build(self, replies):
        transport = Mock()
        transport.post_json.side_effect = [response(text) for text in replies]
        engine = LMStudioChatDialogueEngine(api_key="test", transport=transport)
        context = DialogueContext((), 0, (), (DialogueTurn("开发者是什么", "开发者负责设计与实现软件。"),))
        return engine, transport, context

    def test_identical_speech_retries_once(self):
        engine, transport, context = self.build(["开发者负责设计与实现软件！", "开发者就是做软件的人。"])
        result = engine.respond("更简单一点呢", context)
        self.assertEqual(result.speech, "开发者就是做软件的人。")
        self.assertEqual(transport.post_json.call_count, 2)

    def test_repeated_failure_has_explicit_feedback(self):
        engine, transport, context = self.build(["开发者负责设计与实现软件。"] * 2)
        result = engine.respond("更学术一点", context)
        self.assertIn("没能完成改写", result.speech)
        self.assertIsNone(result.memory_candidate)
        self.assertEqual(transport.post_json.call_count, 2)

    def test_success_and_ordinary_question_do_not_retry(self):
        for question, reply in (("更简单一点", "写程序的人。"), ("开发者是什么", "开发者负责设计与实现软件。")):
            engine, transport, context = self.build([reply])
            engine.respond(question, context)
            self.assertEqual(transport.post_json.call_count, 1)

    def test_style_detection_excludes_negation_and_quotes(self):
        for text in ("不要更简单一点", "他说‘更简单一点’是什么意思", "学术是什么"):
            self.assertIsNone(LMStudioChatDialogueEngine._rewrite_style(text))
        self.assertEqual(LMStudioChatDialogueEngine._rewrite_style("可不可以说得学术一点"), "academic")
        self.assertEqual(LMStudioChatDialogueEngine._rewrite_style("更简单一点呢"), "simple")

