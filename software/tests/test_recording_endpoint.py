import io
import importlib.util
import struct
import sys
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from test_orchestrator import build_test_subject
from pet_yaya.adapters.voice import WindowsVoice
from pet_yaya.domain.cancellation import CancellationToken, DialogueCancelled


@unittest.skipUnless(sys.platform == "win32" and importlib.util.find_spec("numpy"), "Optional Windows audio dependencies required")
class RecordingTests(unittest.TestCase):
    def simulate(self, *, silent=False, key=None, automatic=True):
        import numpy  # Load native extension before patch.dict temporarily replaces module entries.
        clock = [0.0]
        count = [0]
        closed = []
        class Stream:
            def __init__(self, **kwargs):
                self.callback = kwargs["callback"]
            def emit(self):
                value = 0 if silent or count[0] >= 8 else 1000
                self.callback(struct.pack("<h", value)*512, 512, None, False)
                count[0] += 1
            def __enter__(self):
                self.emit()
                return self
            def __exit__(self, *args):
                closed.append(True)
        streams = []
        def make_stream(**kwargs):
            stream = Stream(**kwargs)
            streams.append(stream)
            return stream
        def sleep(seconds):
            clock[0] += 0.032
            streams[0].emit()
        sd = types.SimpleNamespace(query_devices=lambda *args: {"default_samplerate": 16000},
                                   check_input_settings=lambda **kwargs: None, RawInputStream=make_stream)
        keyboard = types.SimpleNamespace(kbhit=lambda: key is not None and count[0] >= 12, getwch=lambda: key)
        class VAD:
            def probability(self, data):
                return 0.9 if data[0:2] != b"\x00\x00" else 0.01
        voice = WindowsVoice()
        voice.auto_end = automatic
        with patch.dict(sys.modules, {"sounddevice": sd, "msvcrt": keyboard}), \
             patch("pet_yaya.adapters.live_vad.LiveSpeechDetector", VAD), \
             patch("sys.stdin.isatty", return_value=True), \
             patch("pet_yaya.adapters.voice.time.monotonic", side_effect=lambda: clock[0]), \
             patch("pet_yaya.adapters.voice.time.sleep", side_effect=sleep), redirect_stdout(io.StringIO()):
            try:
                return voice.record(CancellationToken()), clock[0]
            finally:
                voice.close()
                self.assertEqual(closed, [True])

    def test_recording_stops_automatically_and_keeps_audio(self):
        (audio, rate), elapsed = self.simulate()
        self.assertEqual(rate, 16000)
        self.assertGreater(len(audio), 0)
        self.assertGreater(elapsed, 2.5)
        self.assertLess(elapsed, 3.5)

    def test_silence_releases_microphone_without_audio_submission(self):
        with self.assertRaisesRegex(RuntimeError, "未检测到有效人声"):
            self.simulate(silent=True)

    def test_enter_ends_recording_early(self):
        (_, _), elapsed = self.simulate(key="\r")
        self.assertLess(elapsed, 0.5)

    def test_ctrl_c_releases_microphone(self):
        with self.assertRaises(DialogueCancelled):
            self.simulate(key="\x03")

    def test_manual_mode_does_not_auto_end_on_pause(self):
        (_, _), elapsed = self.simulate(automatic=False)
        self.assertGreaterEqual(elapsed, 15)

