"""No microphone recording: inspect devices or test synthetic Chinese WAV round trip."""
import argparse
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parent / "src"))
from pet_yaya.adapters.voice import WindowsVoice, SOFTWARE
from pet_yaya.domain.cancellation import CancellationToken


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--roundtrip", action="store_true")
    parser.add_argument("--vocabulary", action="store_true", help="Check common words with synthetic audio")
    parser.add_argument("--dialogue", action="store_true", help="Also test running local Qwen with a temporary database")
    args = parser.parse_args()
    import sounddevice as sd
    print(sd.query_devices())
    device = sd.query_devices(kind="input")
    sd.check_input_settings(channels=1, dtype="int16", samplerate=device["default_samplerate"])
    print("Default microphone format supported (not recording).")
    if args.roundtrip or args.dialogue or args.vocabulary:
        directory = SOFTWARE / "data" / "voice-temp"
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as folder:
            wav = Path(folder) / "synthetic.wav"
            voice = WindowsVoice()
            voice.speak("你好，请给我讲一个关于机器人的故事。", CancellationToken(), output_path=wav)
            assert wav.stat().st_size > 1000, "TTS produced no audio"
            text = voice.transcribe(wav, CancellationToken())
            print("Synthetic audio recognized:", text)
            assert "故事" in text and "机器人" in text, text
            if args.vocabulary:
                import time
                print(f"Recognition model: {voice.model_path.name}")
                for sentence, expected in [("你好丫丫，请为我解释一下宇航员的意思。", "宇航员"),
                                            ("请记住，我喜欢恐龙。", "恐龙")]:
                    voice.speak(sentence, CancellationToken(), output_path=wav)
                    started = time.monotonic()
                    recognized = voice.transcribe(wav, CancellationToken())
                    print(f"Vocabulary: {recognized} ({time.monotonic() - started:.2f}s)")
                    assert expected in recognized, recognized
            if args.dialogue:
                from pet_yaya.bootstrap import build_simulator
                from pet_yaya.config import DialogueSettings
                yaya = build_simulator(database_path=Path(folder) / "test.db",
                                       dialogue_settings=DialogueSettings(mode="local", timeout_seconds=60))
                result = yaya.interact(text)
                assert yaya.dialogue_status().active_provider == "local", yaya.dialogue_status()
                voice.speak(result.speech, CancellationToken(), output_path=Path(folder) / "reply.wav")
                assert (Path(folder) / "reply.wav").stat().st_size > 1000
                yaya.shutdown()
                print("PASS: recognized text -> local Qwen -> response WAV (temporary database only).")
        print("PASS: Chinese TTS -> WAV -> local STT; no live recording or speaker playback.")


if __name__ == "__main__":
    main()

