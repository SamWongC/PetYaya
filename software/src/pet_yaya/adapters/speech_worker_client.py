"""Single-flight persistent worker; cancellation kills it to discard stale results."""
import atexit
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from pet_yaya.domain.cancellation import DialogueCancelled


class SpeechWorkerClient:
    def __init__(self, command=None):
        self.requested_device = os.environ.get("PET_YAYA_STT_DEVICE", "cpu")
        if self.requested_device not in {"cpu", "cuda", "auto"}:
            raise ValueError("PET_YAYA_STT_DEVICE must be cpu, cuda or auto")
        self.device = "cuda" if self.requested_device == "auto" else self.requested_device
        self.fallback_reason = None
        self.command = command or [sys.executable, "-X", "utf8", "-u",
                                   str(Path(__file__).with_name("whisper_worker.py")), "--serve"]
        self.process = None
        self.reader = None
        self.lock = threading.Lock()
        atexit.register(self.close)

    def _start(self):
        env = os.environ.copy()
        env.update(PYTHONUTF8="1", HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
        env["PET_YAYA_STT_DEVICE"] = self.device
        self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, env=env,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.results = queue.Queue(maxsize=4)
        process, results = self.process, self.results

        def read():
            try:
                while True:
                    line = process.stdout.readline(16385)
                    if not line or len(line) > 16384:
                        results.put_nowait(None)
                        return
                    results.put_nowait(line)
            except (OSError, ValueError, queue.Full):
                try:
                    results.put_nowait(None)
                except queue.Full:
                    pass

        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def request(self, model_path, audio_path, token, *, confirmation=False, timeout=120):
        if not self.lock.acquire(blocking=False):
            raise RuntimeError("语音识别正在处理另一条输入。")
        try:
            try:
                result = self._request_once(model_path, audio_path, token, confirmation=confirmation, timeout=timeout)
            except DialogueCancelled:
                raise
            except (RuntimeError, OSError) as error:
                if self.requested_device != "auto" or self.device != "cuda":
                    raise
                token.check()
                self.fallback_reason = str(error)
                self.device = "cpu"
                result = self._request_once(model_path, audio_path, token, confirmation=confirmation, timeout=timeout)
            return {**result, "fallback_reason": self.fallback_reason}
        finally:
            self.lock.release()

    def _request_once(self, model_path, audio_path, token, *, confirmation=False, timeout=120):
        try:
            token.check()
            if self.process is None or self.process.poll() is not None:
                self.close()
                self._start()
            payload = {"model": str(model_path), "audio": str(audio_path), "confirmation": confirmation}
            self.process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
            self.process.stdin.flush()
            deadline = time.monotonic() + timeout
            while True:
                token.check()
                if time.monotonic() >= deadline:
                    raise RuntimeError("语音识别超时，后台已重置。")
                try:
                    line = self.results.get(timeout=0.05)
                    break
                except queue.Empty:
                    continue
            token.check()
            if line is None:
                raise RuntimeError("语音识别后台退出，下次输入将重新启动。")
            result = json.loads(line)
            if not isinstance(result, dict) or not isinstance(result.get("text"), str):
                raise RuntimeError("语音识别失败：" + str(result.get("error", "返回格式错误") if isinstance(result, dict) else "返回格式错误"))
            return result
        except BaseException:
            self.close()
            raise

    def close(self):
        process, reader = self.process, self.reader
        self.process = self.reader = None
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
            if reader is not None:
                reader.join(timeout=1)
            process.stdin.close()
            process.stdout.close()

