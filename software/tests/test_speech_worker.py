import sys
import threading
import unittest
import os
from unittest.mock import patch
from test_orchestrator import build_test_subject
from pet_yaya.adapters.speech_worker_client import SpeechWorkerClient
from pet_yaya.domain.cancellation import CancellationToken, DialogueCancelled

FAKE = """
import sys,json,time,os
for line in sys.stdin:
    data=json.loads(line)
    if data['audio']=='sleep': time.sleep(10)
    if data['audio']=='exit': sys.exit(1)
    if data['audio']=='invalid':
        print('invalid',flush=True)
    else:
        print(json.dumps({'text':data['audio'], 'pid':os.getpid()}),flush=True)
"""


class WorkerTests(unittest.TestCase):
    def test_auto_retries_on_cpu_once_and_remembers_fallback(self):
        with patch.dict(os.environ, {"PET_YAYA_STT_DEVICE": "auto"}):
            client = SpeechWorkerClient()
        self.addCleanup(client.close)
        with patch.object(client, "_request_once", side_effect=[RuntimeError("CUDA unavailable"), {"text": "ok"}, {"text": "next"}]) as call:
            result = client.request("model", "audio", CancellationToken())
            self.assertEqual(client.device, "cpu")
            self.assertIn("CUDA", result["fallback_reason"])
            client.request("model", "audio", CancellationToken())
            self.assertEqual(call.call_count, 3)

    def test_auto_cancellation_does_not_retry(self):
        with patch.dict(os.environ, {"PET_YAYA_STT_DEVICE": "auto"}):
            client = SpeechWorkerClient()
        self.addCleanup(client.close)
        with patch.object(client, "_request_once", side_effect=DialogueCancelled()) as call:
            with self.assertRaises(DialogueCancelled):
                client.request("model", "audio", CancellationToken())
            call.assert_called_once()

    def test_strict_cuda_failure_is_not_hidden(self):
        with patch.dict(os.environ, {"PET_YAYA_STT_DEVICE": "cuda"}):
            client = SpeechWorkerClient()
        self.addCleanup(client.close)
        with patch.object(client, "_request_once", side_effect=RuntimeError("CUDA unavailable")) as call:
            with self.assertRaises(RuntimeError):
                client.request("model", "audio", CancellationToken())
            call.assert_called_once()

    def setUp(self):
        self.client = SpeechWorkerClient([sys.executable, "-u", "-c", FAKE])
        self.addCleanup(self.client.close)

    def request(self, audio, token=None, **kwargs):
        return self.client.request("model", audio, token or CancellationToken(), **kwargs)

    def test_multiple_requests_reuse_same_process(self):
        one = self.request("one")
        two = self.request("two")
        self.assertEqual(one["pid"], two["pid"])
        self.assertEqual(two["text"], "two")

    def test_cancel_reaps_and_next_request_has_no_stale_result(self):
        self.request("warm")
        process = self.client.process
        token = CancellationToken()
        timer = threading.Timer(0.15, token.cancel)
        timer.start()
        try:
            with self.assertRaises(DialogueCancelled):
                self.request("sleep", token)
        finally:
            timer.cancel()
        self.assertIsNotNone(process.poll())
        self.assertEqual(self.request("fresh")["text"], "fresh")

    def test_timeout_restarts(self):
        with self.assertRaisesRegex(RuntimeError, "超时"):
            self.request("sleep", timeout=0.15)
        self.assertEqual(self.request("fresh")["text"], "fresh")

    def test_crash_and_invalid_response_recover(self):
        for audio in ("exit", "invalid"):
            with self.subTest(audio=audio):
                with self.assertRaises((RuntimeError, ValueError)):
                    self.request(audio)
                self.assertEqual(self.request("fresh")["text"], "fresh")

    def test_close_reaps_idle_process_and_is_idempotent(self):
        self.request("warm")
        process = self.client.process
        self.client.close()
        self.client.close()
        self.assertIsNotNone(process.poll())

    def test_cancelled_token_does_not_start_worker(self):
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(DialogueCancelled):
            self.request("unused", token)
        self.assertIsNone(self.client.process)

