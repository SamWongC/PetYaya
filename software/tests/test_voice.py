import io
import sys
from pathlib import Path
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from test_orchestrator import build_test_subject
from pet_yaya.main import main
from pet_yaya.adapters.voice import WindowsVoice, run_cancellable
from pet_yaya.domain.cancellation import CancellationToken, DialogueCancelled
from pet_yaya.domain.voice_confirmation import parse_memory_confirmation


class VoiceTests(unittest.TestCase):
    def run_cli(self, entries, voice):
        subject, _, _ = build_test_subject()
        with patch("pet_yaya.main.build_simulator", return_value=subject), \
             patch("builtins.input", side_effect=entries), redirect_stdout(io.StringIO()) as output:
            main(voice=voice)
        return subject, output.getvalue()

    def voice(self, text="你好"):
        voice = Mock(enabled=True)
        voice.listen.return_value = text
        return voice

    def test_confirmed_transcript_enters_normal_dialogue(self):
        voice = self.voice()
        subject, _ = self.run_cli(["/listen", "/quit"], voice)
        self.assertEqual(subject.growth_state().interaction_count, 1)
        voice.speak.assert_called_once()

    def test_mute_does_not_open_microphone(self):
        voice = self.voice()
        subject, _ = self.run_cli(["/mute", "/listen", "/quit"], voice)
        voice.listen.assert_not_called()
        self.assertEqual(subject.growth_state().interaction_count, 0)

    def test_cancelled_transcript_does_not_commit(self):
        subject, _ = self.run_cli(["/review on", "/listen", "/cancel", "/quit"], self.voice())
        self.assertEqual(subject.growth_state().interaction_count, 0)

    def test_recognized_commands_are_not_executed(self):
        subject, output = self.run_cli(["/listen", "", "/quit"], self.voice("/reset yes"))
        self.assertIn("不执行管理命令", output)
        self.assertEqual(subject.growth_state().interaction_count, 0)

    def test_pending_memory_requires_typed_approval(self):
        voice = self.voice("请记住我喜欢恐龙")
        subject, _ = self.run_cli(["/voice off", "/listen", "/listen", "/yes", "/quit"], voice)
        voice.listen.assert_called_once()
        self.assertEqual(len(subject.list_memories()), 1)

    def test_recognition_error_is_recoverable(self):
        voice = self.voice()
        voice.listen.side_effect = RuntimeError("microphone unavailable")
        subject, _ = self.run_cli(["/listen", "你好", "/quit"], voice)
        self.assertEqual(subject.growth_state().interaction_count, 1)

    def test_cancelled_playback_keeps_completed_growth(self):
        voice = self.voice()
        voice.speak.side_effect = DialogueCancelled()
        subject, output = self.run_cli(["你好", "/growth", "/quit"], voice)
        self.assertEqual(subject.growth_state().interaction_count, 1)
        self.assertIn("朗读已停止", output)

    def test_voice_off_skips_playback(self):
        voice = self.voice()
        self.run_cli(["/voice off", "你好", "/quit"], voice)
        voice.speak.assert_not_called()

    def test_corrected_transcript_replaces_recognized_text(self):
        subject, _ = self.run_cli(["/review on", "/voice off", "/listen", "请记住我喜欢星星", "/yes", "/quit"], self.voice())
        self.assertIn("星星", subject.list_memories()[0].content)

    def test_missing_model_never_records(self):
        voice = WindowsVoice()
        with tempfile.TemporaryDirectory() as directory:
            voice.model_path = Path(directory)
            with patch.object(voice, "record") as record:
                with self.assertRaisesRegex(RuntimeError, "缺少"):
                    voice.listen(CancellationToken())
                record.assert_not_called()

    def test_consent_requires_whole_explicit_phrase(self):
        for text in ("确认。", "记住吧！", "確認保存", "不要", "算了"):
            self.assertIsNotNone(parse_memory_confirmation(text))
        for text in ("", "可以吗？", "不要确认", "确认，不要", "我说过记住吧吗", "嗯", "/yes"):
            self.assertIsNone(parse_memory_confirmation(text))

    def test_voice_consent_commits_once_without_extra_growth(self):
        voice = self.voice()
        voice.listen.side_effect = ["请记住我喜欢恐龙", "记住吧"]
        subject, _ = self.run_cli(["/listen", "/quit"], voice)
        self.assertEqual(len(subject.list_memories()), 1)
        self.assertEqual(subject.growth_state().interaction_count, 1)
        self.assertEqual(voice.listen.call_args.kwargs, {"confirmation": True})
        self.assertEqual(voice.speak.call_count, 2)

    def test_ambiguous_negative_silent_and_cancelled_confirmation_do_not_save(self):
        for response in ("不要", "可能吧", "", RuntimeError("silence"), DialogueCancelled()):
            with self.subTest(response=response):
                voice = self.voice()
                voice.listen.side_effect = ["请记住我喜欢恐龙", response]
                subject, _ = self.run_cli(["/listen", "你好", "/quit"], voice)
                self.assertEqual(len(subject.list_memories()), 0)
                self.assertEqual(subject.growth_state().interaction_count, 2)

    def test_cancelled_or_failed_question_never_auto_records(self):
        for error in (DialogueCancelled(), RuntimeError("speaker failed")):
            voice = self.voice("请记住我喜欢恐龙")
            voice.speak.side_effect = error
            subject, _ = self.run_cli(["/listen", "/no", "/quit"], voice)
            voice.listen.assert_called_once()
            self.assertEqual(len(subject.list_memories()), 0)

    def test_typed_memory_does_not_auto_record(self):
        voice = self.voice()
        self.run_cli(["请记住我喜欢恐龙", "/no", "/quit"], voice)
        voice.listen.assert_not_called()

    def test_feedback_failure_does_not_undo_approved_memory(self):
        voice = self.voice()
        voice.listen.side_effect = ["请记住我喜欢恐龙", "确认"]
        voice.speak.side_effect = [None, RuntimeError("speaker failed")]
        subject, _ = self.run_cli(["/listen", "/quit"], voice)
        self.assertEqual(len(subject.list_memories()), 1)

    def test_temporary_recording_cleaned_on_success_and_cancel(self):
        for cancel in (False, True):
            with self.subTest(cancel=cancel), tempfile.TemporaryDirectory() as directory:
                voice = WindowsVoice()
                voice.model_path = Path(directory)
                saved = []
                def transcribe(path, token, **kwargs):
                    self.assertTrue(path.exists())
                    saved.append(path)
                    if cancel:
                        raise DialogueCancelled()
                    return "你好"
                with patch("pet_yaya.adapters.voice.SOFTWARE", Path(directory)), \
                     patch("pathlib.Path.is_file", return_value=True), \
                     patch.object(voice, "record", return_value=(b"\x00\x00" * 100, 16000)), \
                     patch.object(voice, "transcribe", side_effect=transcribe), redirect_stdout(io.StringIO()):
                    if cancel:
                        with self.assertRaises(DialogueCancelled):
                            voice.listen(CancellationToken())
                    else:
                        self.assertEqual(voice.listen(CancellationToken()), "你好")
                self.assertFalse(saved[0].exists())

    def test_subprocess_cancellation_reaps_worker(self):
        token = CancellationToken()
        timer = threading.Timer(0.2, token.cancel)
        timer.start()
        try:
            with self.assertRaises(DialogueCancelled):
                run_cancellable([sys.executable, "-c", "import time; time.sleep(10)"], token)
        finally:
            timer.cancel()

    def test_subprocess_timeout_and_failure(self):
        with self.assertRaisesRegex(RuntimeError, "超时"):
            run_cancellable([sys.executable, "-c", "import time; time.sleep(10)"],
                            CancellationToken(), timeout=0.1)
        with self.assertRaisesRegex(RuntimeError, "失败"):
            run_cancellable([sys.executable, "-c", "raise ValueError('test')"], CancellationToken())

    def test_tts_passes_text_as_data_not_command(self):
        text = "$(Remove-Item secret); <speak>你好</speak>"
        with patch("pet_yaya.adapters.voice.run_cancellable") as run:
            WindowsVoice().speak(text, CancellationToken())
        self.assertNotIn(text, run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs["input_text"], text)


if __name__ == "__main__":
    unittest.main()

