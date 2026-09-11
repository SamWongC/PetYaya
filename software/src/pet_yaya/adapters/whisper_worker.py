"""Persistent isolated transcription; lazy model cache, no runtime downloads."""
import json
import sys
import time
import os
from cuda_runtime import configure_cuda_dlls
_dll_handles = configure_cuda_dlls()
from faster_whisper import WhisperModel
from speech_recognition import transcription_options


def recognize(models, model_path, audio_path, confirmation=False):
    started = time.monotonic()
    cached = model_path in models
    if not cached:
        # The client uses at most the configured chat and confirmation model.
        if len(models) >= 2:
            models.clear()
        device = os.environ.get("PET_YAYA_STT_DEVICE", "cpu")
        if device not in {"cpu", "cuda"}:
            raise ValueError("PET_YAYA_STT_DEVICE must be cpu or cuda")
        models[model_path] = WhisperModel(model_path, device=device,
                                          compute_type="int8_float16" if device == "cuda" else "int8",
                                          cpu_threads=4, local_files_only=True)
    loaded = time.monotonic()
    options = transcription_options(confirmation=confirmation)
    segments, _ = models[model_path].transcribe(audio_path, **options)
    text = "".join(segment.text for segment in segments).strip()
    return {"text": text, "cached": cached, "device": os.environ.get("PET_YAYA_STT_DEVICE", "cpu"), "load_seconds": loaded - started,
            "recognition_seconds": time.monotonic() - loaded}


def main():
    models = {}
    if sys.argv[1:] == ["--serve"]:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                result = recognize(models, request["model"], request["audio"], request.get("confirmation", False))
            except Exception as error:
                result = {"error": str(error)[:400]}
            print(json.dumps(result, ensure_ascii=True), flush=True)
    else:
        result = recognize(models, sys.argv[1], sys.argv[2], "--confirmation" in sys.argv[3:])
        print(json.dumps(result, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()

