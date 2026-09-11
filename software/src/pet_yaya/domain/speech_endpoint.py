"""Deterministic end-of-utterance policy fed by speech probabilities."""
class SpeechEndpoint:
    def __init__(self, *, silence_seconds=2.5, initial_timeout=5.0, max_seconds=15.0):
        self.silence_seconds = silence_seconds
        self.initial_timeout = initial_timeout
        self.max_seconds = max_seconds
        self.elapsed = 0.0
        self.last_speech = 0.0
        self.onset = 0.0
        self.heard_speech = False
        self.reason = None

    def feed(self, probability, seconds=0.032):
        if self.reason is not None:
            return self.reason
        self.elapsed += seconds
        if probability >= (0.35 if self.heard_speech else 0.6):
            self.onset += seconds
            if self.onset >= 0.096:
                self.heard_speech = True
            if self.heard_speech:
                self.last_speech = self.elapsed
        else:
            self.onset = 0.0
        if self.heard_speech and self.elapsed - self.last_speech >= self.silence_seconds:
            self.reason = "silence"
        elif not self.heard_speech and self.elapsed >= self.initial_timeout:
            self.reason = "no_speech"
        elif self.elapsed >= self.max_seconds:
            self.reason = "limit"
        return self.reason

