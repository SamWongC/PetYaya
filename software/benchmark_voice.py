"""Synthetic audio only. No microphone, playback, cloud, or personal database."""
from pathlib import Path
import sys
import tempfile
import json
import argparse
import os
import subprocess

sys.path.insert(0, str(Path(__file__).parent / "src"))
from pet_yaya.adapters.voice import WindowsVoice, SOFTWARE
from pet_yaya.domain.cancellation import CancellationToken


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--dialogue", action="store_true", help="Test Qwen while both recognizers remain loaded")
    args = parser.parse_args()
    os.environ["PET_YAYA_STT_DEVICE"] = args.device
    voice = WindowsVoice()
    folder = SOFTWARE / "data" / "voice-temp"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(dir=folder) as directory:
            wav = Path(directory) / "synthetic.wav"
            voice.speak("请为我解释一下宇航员的意思。", CancellationToken(), output_path=wav)
            print(f"model={voice.model_path.name}; device={args.device}; same audio every round", flush=True)
            for i in range(3):
                text = voice.transcribe(wav, CancellationToken())
                print(json.dumps({"round": i + 1, **voice.last_recognition}, ensure_ascii=False), flush=True)
                assert "宇航员" in text, text
                assert voice.last_recognition["cached"] == (i > 0)
            if args.dialogue:
                from pet_yaya.bootstrap import build_simulator
                from pet_yaya.config import DialogueSettings
                from pet_yaya.domain.voice_confirmation import parse_memory_confirmation
                voice.speak("请记住，我喜欢恐龙。", CancellationToken(), output_path=wav)
                text = voice.transcribe(wav, CancellationToken())
                assert "恐龙" in text, text
                print("Vocabulary:", voice.last_recognition, flush=True)
                voice.speak("记住吧。", CancellationToken(), output_path=wav)
                text = voice.transcribe(wav, CancellationToken(), confirmation=True)
                assert parse_memory_confirmation(text) is True, text
                print("Confirmation:", voice.last_recognition, flush=True)
                voice.speak("不要。", CancellationToken(), output_path=wav)
                text = voice.transcribe(wav, CancellationToken(), confirmation=True)
                assert parse_memory_confirmation(text) is False, text
                print("Rejection:", voice.last_recognition, flush=True)
                print(subprocess.check_output(["nvidia-smi", "--query-gpu=memory.total,memory.used",
                                               "--format=csv"], text=True), flush=True)
                yaya = build_simulator(database_path=Path(directory) / "test.db",
                                       dialogue_settings=DialogueSettings(mode="local", timeout_seconds=60))
                try:
                    yaya.interact("请用一句话解释宇航员的意思。")
                    assert yaya.dialogue_status().active_provider == "local", yaya.dialogue_status()
                finally:
                    yaya.shutdown()
                print("PASS: both recognizers resident, Qwen response succeeded.", flush=True)
    finally:
        voice.close()


if __name__ == "__main__":
    main()

