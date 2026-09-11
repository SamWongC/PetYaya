"""One-time model download into the project. Install requirements-voice.txt first."""
import os
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ["HF_HOME"] = str(ROOT / "models" / ".hf-cache")
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=("small", "medium"), default="small")
    args = parser.parse_args()
    from faster_whisper.utils import download_model
    path = download_model(args.model, output_dir=str(ROOT / "models" / f"faster-whisper-{args.model}"))
    print(f"Speech model ready: {path}")

