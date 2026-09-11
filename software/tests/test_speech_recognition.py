import unittest
import os
from pathlib import Path
from unittest.mock import patch
from test_orchestrator import build_test_subject
from pet_yaya.adapters.speech_recognition import transcription_options
from pet_yaya.adapters.voice import WindowsVoice, DEFAULT_MODEL, ACCURATE_MODEL
from pet_yaya.domain.cancellation import CancellationToken


class RecognitionTests(unittest.TestCase):
    def test_medium_chat_keeps_small_confirmation(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(Path, "is_file", return_value=True):
            voice = WindowsVoice()
        self.assertEqual(voice.model_path, ACCURATE_MODEL)
        self.assertEqual(voice.confirmation_model_path, DEFAULT_MODEL)

    def test_explicit_model_override_applies_to_both_stages(self):
        with patch.dict(os.environ, {"PET_YAYA_STT_MODEL": "custom-model", "PET_YAYA_MIC_DEVICE": ""}):
            voice = WindowsVoice()
        self.assertEqual(voice.model_path, Path("custom-model"))
        self.assertEqual(voice.confirmation_model_path, Path("custom-model"))

    def test_common_vocabulary_and_more_search_candidates(self):
        options = transcription_options()
        self.assertEqual(options["beam_size"], 5)
        self.assertIn("宇航员", options["hotwords"])
        self.assertIn("恐龙", options["hotwords"])

    def test_confirmation_has_no_positive_answer_bias(self):
        options = transcription_options(confirmation=True)
        self.assertNotIn("initial_prompt", options)
        self.assertNotIn("hotwords", options)

    def test_missing_vocabulary_is_optional(self):
        with patch.object(Path, "is_file", return_value=False):
            self.assertNotIn("hotwords", transcription_options())

    def test_confirmation_mode_reaches_worker_and_no_word_replacement(self):
        with patch.object(Path, "is_file", return_value=True), \
             patch("pet_yaya.adapters.voice.SpeechWorkerClient.request", return_value={"text":"鱼航员"}) as run:
            text = WindowsVoice().transcribe("test.wav", CancellationToken(), confirmation=True)
        self.assertTrue(run.call_args.kwargs["confirmation"])
        self.assertEqual(text, "鱼航员")

