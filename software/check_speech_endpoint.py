"""Test bundled live VAD with synthetic speech, silence and clicks; never record."""
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).parent / "src"))
from pet_yaya.adapters.live_vad import LiveSpeechDetector
from pet_yaya.domain.speech_endpoint import SpeechEndpoint
from pet_yaya.adapters.voice import WindowsVoice, SOFTWARE
from pet_yaya.domain.cancellation import CancellationToken


def detect(audio, confirmation=False):
    import numpy as np
    vad = LiveSpeechDetector()
    endpoint = SpeechEndpoint(silence_seconds=0.8 if confirmation else 2.5,
                              max_seconds=5 if confirmation else 15)
    for start in range(0, len(audio) - 511, 512):
        pcm = (np.clip(audio[start:start+512], -1, 1) * 32767).astype(np.int16).tobytes()
        if endpoint.feed(vad.probability(pcm)):
            break
    return endpoint


def main():
    import numpy as np
    from faster_whisper.audio import decode_audio
    voice = WindowsVoice()
    folder = SOFTWARE / "data" / "voice-temp"
    folder.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(dir=folder) as directory:
            wav = Path(directory) / "sample.wav"
            for text, confirmation in [("请给我讲一个关于恐龙的故事。", False), ("可以啊。", True)]:
                voice.speak(text, CancellationToken(), output_path=wav)
                samples = decode_audio(str(wav), sampling_rate=16000)
                endpoint = detect(np.concatenate([samples, np.zeros(56000, dtype=np.float32)]), confirmation)
                print(f"{text} speech={endpoint.heard_speech} end={endpoint.reason} at={endpoint.elapsed:.2f}s", flush=True)
                assert endpoint.heard_speech and endpoint.reason == "silence"
                assert endpoint.elapsed >= len(samples)/16000 - 0.4, "Ended before speech finished"
                if not confirmation:
                    # A two-second thinking pause must not split the two phrases.
                    active = np.flatnonzero(np.abs(samples) > 0.005)
                    trimmed = samples[max(0, active[0]-800):min(len(samples), active[-1]+800)]
                    joined = np.concatenate([trimmed, np.zeros(32000, dtype=np.float32), trimmed, np.zeros(56000, dtype=np.float32)])
                    endpoint = detect(joined)
                    assert endpoint.reason == "silence" and endpoint.elapsed > 2*len(trimmed)/16000, (endpoint.reason, endpoint.elapsed, len(trimmed)/16000)
                    print("PASS: two-second pause did not cut the second phrase", flush=True)
            silence = np.zeros(82000, dtype=np.float32)
            assert detect(silence).reason == "no_speech"
            clicks = silence.copy()
            clicks[::8000] = 0.8
            assert detect(clicks).reason == "no_speech"
            print("PASS: silence and synthetic impulses did not become speech. No microphone or playback used.")
    finally:
        voice.close()


if __name__ == "__main__":
    main()

