"""Run Yaya in its own Python console, without a waiting batch shell."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))


def prepare_local_model():
    lms = shutil.which("lms")
    if not lms:
        candidate = Path.home() / ".lmstudio" / "bin" / "lms.exe"
        if not candidate.is_file():
            raise RuntimeError("LM Studio CLI (lms) was not found.")
        lms = str(candidate)
    subprocess.run([lms, "daemon", "up"], check=True)
    subprocess.run([lms, "server", "start", "--port", "1234", "--bind", "127.0.0.1"], check=True)
    model = os.environ.get("PET_YAYA_LOCAL_MODEL", "").strip() or "qwen/qwen3.5-9b"
    listing = subprocess.run([lms, "ps", "--json"], check=True, capture_output=True, encoding="utf-8")
    loaded = json.loads(listing.stdout)
    if any(item.get("modelKey") == model or item.get("identifier") == model for item in loaded):
        print(f"Local model is already loaded: {model}", flush=True)
    else:
        subprocess.run([lms, "load", model, "--gpu", "max", "--context-length", "8192", "--yes"], check=True)
    os.environ.update({
        "PET_YAYA_DIALOGUE_MODE": "local",
        "PET_YAYA_LOCAL_MODEL": model,
        "PET_YAYA_LOCAL_BASE_URL": "http://127.0.0.1:1234/v1",
        "PET_YAYA_LOCAL_API_TOKEN": "lm-studio",
    })


def main():
    parser = argparse.ArgumentParser(description="Pet Yaya standalone console")
    parser.add_argument("--local", action="store_true", help="Start LM Studio and Qwen first")
    parser.add_argument("--voice", action="store_true", help="Enable optional Windows speech")
    args = parser.parse_args()
    try:
        if args.local:
            prepare_local_model()
        from pet_yaya.main import main as run_yaya
        voice = None
        if args.voice:
            from pet_yaya.adapters.voice import WindowsVoice
            voice = WindowsVoice()
        run_yaya(voice=voice)
    except KeyboardInterrupt:
        print("\nStartup cancelled.")
    except Exception as error:
        print(f"Startup failed: {error}", file=sys.stderr)
        if sys.stdin.isatty():
            input("Press Enter to close...")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

