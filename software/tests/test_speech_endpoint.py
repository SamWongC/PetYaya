import unittest
from test_orchestrator import build_test_subject
from pet_yaya.domain.speech_endpoint import SpeechEndpoint


def frames(detector, probability, count):
    result = None
    for _ in range(count):
        result = detector.feed(probability)
    return result


class EndpointTests(unittest.TestCase):
    def test_silence_times_out_without_speech(self):
        detector = SpeechEndpoint()
        self.assertEqual(frames(detector, 0.01, 157), "no_speech")
        self.assertFalse(detector.heard_speech)

    def test_short_pause_does_not_end_sentence(self):
        detector = SpeechEndpoint(silence_seconds=1.2)
        frames(detector, 0.9, 10)
        self.assertIsNone(frames(detector, 0.01, 20))
        frames(detector, 0.9, 10)
        self.assertIsNone(frames(detector, 0.01, 20))
        self.assertEqual(frames(detector, 0.01, 18), "silence")

    def test_two_second_thinking_pause_does_not_end_default_recording(self):
        detector = SpeechEndpoint()
        frames(detector, 0.9, 10)
        self.assertIsNone(frames(detector, 0.01, 63))
        frames(detector, 0.9, 10)
        self.assertIsNone(frames(detector, 0.01, 78))
        self.assertEqual(frames(detector, 0.01, 1), "silence")

    def test_confirmation_ends_after_shorter_pause(self):
        detector = SpeechEndpoint(silence_seconds=0.8, max_seconds=5)
        frames(detector, 0.9, 8)
        self.assertIsNone(frames(detector, 0.0, 24))
        self.assertEqual(frames(detector, 0.0, 2), "silence")

    def test_isolated_clicks_do_not_start_speech(self):
        detector = SpeechEndpoint()
        for _ in range(79):
            detector.feed(0.99)
            detector.feed(0.01)
        self.assertFalse(detector.heard_speech)
        self.assertEqual(detector.reason, "no_speech")

    def test_continuous_voice_respects_recording_limit(self):
        detector = SpeechEndpoint(max_seconds=15)
        self.assertEqual(frames(detector, 0.9, 469), "limit")

    def test_endpoint_is_terminal(self):
        detector = SpeechEndpoint()
        frames(detector, 0.0, 157)
        self.assertEqual(frames(detector, 0.99, 10), "no_speech")

    def test_soft_voice_after_onset_keeps_recording(self):
        detector = SpeechEndpoint()
        frames(detector, 0.9, 3)
        self.assertIsNone(frames(detector, 0.4, 50))

