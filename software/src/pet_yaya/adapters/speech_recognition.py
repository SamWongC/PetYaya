"""Recognition hints, not post-recognition word replacement."""
from pathlib import Path

VOCABULARY = Path(__file__).resolve().parents[3] / "speech_vocabulary.txt"


def transcription_options(*, confirmation=False, vocabulary=VOCABULARY):
    options = dict(language="zh", beam_size=5, temperature=0.0,
                   vad_filter=True, condition_on_previous_text=False)
    # Do not prime the consent recognizer with positive answers or topic vocabulary.
    if confirmation:
        return options
    words = []
    if vocabulary.is_file():
        for line in vocabulary.read_text(encoding="utf-8").splitlines():
            word = line.strip()
            if word and not word.startswith("#") and len(word) <= 24:
                words.append(word)
            if len(words) >= 40:
                break
    options["initial_prompt"] = "普通话对话，使用简体中文和标点。"
    if words:
        options["hotwords"] = "，".join(words)
    return options

