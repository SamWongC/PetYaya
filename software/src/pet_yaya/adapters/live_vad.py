"""Incremental Silero VAD using the ONNX asset bundled with faster-whisper."""
class LiveSpeechDetector:
    def __init__(self):
        import numpy as np
        from faster_whisper.vad import get_vad_model
        self.np = np
        self.session = get_vad_model().session
        self.h = np.zeros((1, 1, 128), dtype=np.float32)
        self.c = np.zeros((1, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, 64), dtype=np.float32)

    def probability(self, pcm):
        np = self.np
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size != 512:
            raise ValueError("Live VAD requires 512 mono PCM16 samples at 16 kHz")
        inputs = np.concatenate([self.context, audio.reshape(1, -1)], axis=1)
        output, self.h, self.c = self.session.run(None, {"input": inputs, "h": self.h, "c": self.c})
        self.context = audio[-64:].reshape(1, -1)
        return float(output.reshape(-1)[-1])

