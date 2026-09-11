"""Optional Windows push-to-talk adapter; imports audio dependencies lazily."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import wave
import queue
import threading
import math

from pet_yaya.domain.cancellation import CancellationToken
from pet_yaya.adapters.speech_worker_client import SpeechWorkerClient
from pet_yaya.domain.speech_endpoint import SpeechEndpoint

SOFTWARE = Path(__file__).resolve().parents[3]
DEFAULT_MODEL = SOFTWARE / "models" / "faster-whisper-small"
ACCURATE_MODEL = SOFTWARE / "models" / "faster-whisper-medium"


def run_cancellable(command, token, *, input_text=None, timeout=120):
    """Drain subprocess pipes without blocking cancellation or leaving a worker."""
    env = os.environ.copy()
    env.update(PYTHONUTF8="1", HF_HUB_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    token.check()
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=env,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    started = time.monotonic()
    data = (input_text or "").encode("utf-8")
    try:
        while True:
            token.check()
            if time.monotonic() - started > timeout:
                raise RuntimeError("语音处理超时，已停止；可以继续文字聊天。")
            try:
                out, err = process.communicate(input=data, timeout=0.05)
                break
            except subprocess.TimeoutExpired:
                data = None
        token.check()
        if process.returncode:
            detail = err.decode("utf-8", errors="replace").strip()[-800:]
            raise RuntimeError(f"语音组件失败：{detail}")
        return out.decode("utf-8").strip()
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


class WindowsVoice:
    def __init__(self):
        preferred = ACCURATE_MODEL if (ACCURATE_MODEL / "model.bin").is_file() else DEFAULT_MODEL
        self.model_path = Path(os.environ.get("PET_YAYA_STT_MODEL", str(preferred)))
        self.confirmation_model_path = (DEFAULT_MODEL if (DEFAULT_MODEL / "model.bin").is_file()
                                        and not os.environ.get("PET_YAYA_STT_MODEL") else self.model_path)
        raw_device = os.environ.get("PET_YAYA_MIC_DEVICE", "").strip()
        self.device = int(raw_device) if raw_device else None
        self.enabled = True
        self.auto_end = True
        self.pause_seconds = 2.5
        self._recognizer = SpeechWorkerClient()
        self.last_recognition = None

    def close(self):
        self._recognizer.close()

    def set_pause(self, seconds):
        value = float(seconds)
        if not math.isfinite(value) or not 1 <= value <= 5:
            raise ValueError("停顿等待时间需要是1到5秒。")
        self.pause_seconds = value

    def record(self, token, *, confirmation=False):
        if os.name != "nt" or not sys.stdin.isatty():
            raise RuntimeError("按键录音需要 Windows 交互式控制台。")
        import msvcrt
        import sounddevice as sd
        import numpy as np

        device = sd.query_devices(self.device, "input")
        rate = 16000 if self.auto_end else int(device["default_samplerate"])
        try:
            sd.check_input_settings(device=self.device, channels=1, dtype="int16", samplerate=rate)
        except Exception as error:
            raise RuntimeError("麦克风格式不可用；自动结束需16kHz单声道，可试 /endpoint off 手动模式。") from error
        detector = None
        if self.auto_end:
            try:
                from pet_yaya.adapters.live_vad import LiveSpeechDetector
                detector = LiveSpeechDetector()
            except Exception as error:
                raise RuntimeError("人声检测初始化失败，可用 /endpoint off 切回手动结束：" + str(error)) from error
        blocks = []
        overflow = threading.Event()
        incoming = queue.Queue(maxsize=64)
        duration = 5 if confirmation else 15
        limit = rate * duration
        captured = 0
        endpoint = SpeechEndpoint(silence_seconds=0.8 if confirmation else self.pause_seconds, max_seconds=duration)
        reason = "limit"

        def receive(data, frames, timing, status):
            nonlocal captured
            if status:
                overflow.set()
            if captured < limit:
                chunk = bytes(data)[: (limit - captured) * 2]
                captured += len(chunk) // 2
                try:
                    incoming.put_nowait(chunk)
                except queue.Full:
                    overflow.set()

        token.check()
        if confirmation:
            # Cue ends before the microphone opens, so it cannot enter recognition.
            import winsound
            winsound.Beep(880, 150)
            token.check()
        with sd.RawInputStream(device=self.device, channels=1, samplerate=rate,
                               blocksize=512 if self.auto_end else 1024, dtype="int16", callback=receive):
            ending = f"检测到连续停顿约{endpoint.silence_seconds:g}秒后结束；Enter 可提前结束" if self.auto_end else "按 Enter 结束"
            print(f"正在录音，请说话。{ending}，Ctrl+C 取消；最长 {duration} 秒。", flush=True)
            started = time.monotonic()
            while time.monotonic() - started < duration:
                token.check()
                if overflow.is_set():
                    raise RuntimeError("录音丢帧或处理跟不上，请重试；也可用 /endpoint off 手动结束。")
                stop = False
                for _ in range(16):
                    try:
                        chunk = incoming.get_nowait()
                    except queue.Empty:
                        break
                    blocks.append(chunk)
                    if detector is not None and len(chunk) == 1024:
                        ended = endpoint.feed(detector.probability(chunk))
                        if ended:
                            reason, stop = ended, True
                            break
                if stop:
                    break
                if msvcrt.kbhit():
                    key = msvcrt.getwch()
                    if key == "\x03":
                        token.cancel()
                        token.check()
                    if key == "\r":
                        reason = "manual"
                        break
                if detector is not None and not endpoint.heard_speech and time.monotonic() - started >= 5:
                    reason = "no_speech"
                    break
                time.sleep(0.02)
        token.check()
        if overflow.is_set():
            raise RuntimeError("录音出现丢帧，请关闭占用音频的程序后重试。")
        if detector is not None and not endpoint.heard_speech:
            raise RuntimeError("未检测到有效人声，本次录音已结束，没有发送或保存。可用 /endpoint off 手动结束录音。")
        if reason == "silence":
            print("检测到说话结束，已自动停止录音。", flush=True)
        elif reason == "limit":
            print(f"已到 {duration} 秒录音上限。", flush=True)
        audio = b"".join(blocks)
        samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32)
        if len(samples) < rate * 0.3 or float(np.sqrt(np.mean(samples ** 2))) < 60:
            raise RuntimeError("没有录到清晰声音，请检查麦克风或靠近后重试。")
        return audio, rate

    def transcribe(self, audio_path, token, *, confirmation=False):
        model_path = self.confirmation_model_path if confirmation else self.model_path
        if not (model_path / "model.bin").is_file():
            raise RuntimeError("缺少本地语音模型，请先运行 setup_voice.py。")
        started = time.monotonic()
        result = self._recognizer.request(model_path, audio_path, token, confirmation=confirmation)
        if result.get("fallback_reason") and not (self.last_recognition or {}).get("fallback_reason"):
            print("GPU 识别不可用，已退回 CPU：" + result["fallback_reason"], flush=True)
        self.last_recognition = {**result, "total_seconds": time.monotonic() - started}
        text = result["text"].strip()
        if not text:
            raise RuntimeError("没有识别到有效语音，请重试。")
        return text

    def listen(self, token, *, confirmation=False):
        if not (self.model_path / "model.bin").is_file():
            raise RuntimeError("缺少本地语音模型，请先运行 setup_voice.py。")
        audio, rate = self.record(token, confirmation=confirmation)
        # Temporary audio stays inside this project and is removed even on cancellation.
        directory = SOFTWARE / "data" / "voice-temp"
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as folder:
            path = Path(folder) / "input.wav"
            with wave.open(str(path), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(rate)
                output.writeframes(audio)
            print("录音结束，正在本地识别（Ctrl+C 可取消）……", flush=True)
            text = self.transcribe(path, token, confirmation=confirmation)
            if self.last_recognition is not None:
                stats = self.last_recognition
                print(f"识别设备：{stats.get('device', 'unknown')}；耗时：{stats['total_seconds']:.2f} 秒", flush=True)
            return text

    def speak(self, text, token, *, output_path=None):
        script = Path(__file__).with_name("speak.ps1")
        powershell = Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        command = [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                   "-File", str(script)]
        if output_path is not None:
            command += ["-OutputPath", str(output_path)]
        run_cancellable(command, token, input_text=text)

