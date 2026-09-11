# Installation and running

These instructions target Windows PowerShell and must be run in **this repository's `software` directory**. The interactive interface and voice examples are Chinese. Do not paste PowerShell environment-variable commands into Command Prompt or into the simulator prompt.

## 1. Create a Python environment

Install a standard Python distribution, version 3.11 or newer. The following example selects Python 3.12 using the Windows Python launcher:

```powershell
cd path\to\PetYaya\software
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe --version
```

Replace the example path with your checkout. Use an installed compatible interpreter if `py -3.12` is unavailable. No environment activation is required for these commands. Do not copy another machine's `.venv` or rely on an interpreter bundled with an unrelated application.

## 2. Run the rules-only baseline

```powershell
$env:PET_YAYA_DIALOGUE_MODE = "rules"
.\.venv\Scripts\python.exe -X utf8 launch_simulator.py
```

This mode needs neither model weights nor network access and is suitable for checking commands, persistence and state handling. It does not provide general-purpose intelligent dialogue. Enter `/quit` before proceeding.

## 3. Run local model dialogue

Prerequisites:

- LM Studio installed, with its `lms` CLI discoverable on `PATH` or at the launcher's supported user-local location.
- A compatible Qwen model already downloaded in LM Studio. The current default identifier is `qwen/qwen3.5-9b`; use the identifier shown by your installation if different.
- Enough memory for the selected model and context size. Hardware capacity affects whether the model loads and how fast it responds; no universal minimum has been established by this project.

```powershell
$env:PET_YAYA_LOCAL_MODEL = "qwen/qwen3.5-9b"
.\.venv\Scripts\python.exe -X utf8 launch_simulator.py --local
```

The launcher starts the LM Studio daemon and loopback server on port 1234, then loads the selected model if necessary, requesting maximum GPU offload and an 8192-token context. It does not download the dialogue model for you.

Inside the simulator, send a normal question, then enter `/model`. Verify that the active provider is `local`, not merely that local mode is configured.

If you need to control model loading manually, load it in LM Studio, start the server yourself, and run without `--local`:

```powershell
$env:PET_YAYA_DIALOGUE_MODE = "local"
$env:PET_YAYA_LOCAL_MODEL = "qwen/qwen3.5-9b"
$env:PET_YAYA_LOCAL_BASE_URL = "http://127.0.0.1:1234/v1"
.\.venv\Scripts\python.exe -X utf8 launch_simulator.py
```

The automatic `--local` launcher sets its own loopback URL and placeholder token. Use manual startup for customized endpoints/authentication. Keep the service local for the intended desktop workflow.

## 4. Add optional speech

Requires a working microphone, speakers/headphones, and a Windows Chinese speech voice available through SAPI. Initial dependency and model downloads need internet access.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-voice.txt
.\.venv\Scripts\python.exe setup_voice.py --model small
.\.venv\Scripts\python.exe setup_voice.py --model medium
```

The medium download is optional. When both models are present, ordinary recognition prefers medium and short memory confirmations can use small. An explicit `PET_YAYA_STT_MODEL` path overrides that selection.

For a compatible NVIDIA GPU and driver, optionally install the project's CUDA library requirements:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-voice-gpu.txt
$env:PET_YAYA_STT_DEVICE = "auto"
```

For a CPU-only configuration, set `PET_YAYA_STT_DEVICE` to `cpu`. GPU recognition is optional and its compatibility must be checked on the target machine.

Start the voice version:

```powershell
.\run_voice_simulator.cmd
```

This opens a separate console, starts the local model, and enables speech. Alternatively, run the Python entry directly with `--local --voice`.

Inside the simulator, enter `/listen`, then speak. Normal recording ends after approximately 2.5 seconds of continuous detected silence, with a 15-second maximum. Enter can finish recording early. Memory confirmation uses a shorter bounded recording window.

## Useful simulator commands

| Command | Purpose |
| --- | --- |
| `/help` | Display available commands |
| `/listen` | Record one spoken turn |
| `/pause 3` | Change normal endpoint silence wait to 3 seconds; allowed range 1–5 |
| `/endpoint off` / `/endpoint on` | Switch manual/automatic recording endpoint |
| `/review on` / `/review off` | Enable/disable transcript review before submission |
| `/memory` | List confirmed long-term memories |
| `/yes` / `/no` | Approve/reject the pending memory |
| `/forget 1` | Delete the memory currently shown as number 1 |
| `/clearhistory` | Clear short-term dialogue context, not long-term memory |
| `/growth` | Inspect growth state |
| `/model` | Inspect active provider and fallback reason |
| `/status` / `/events` | Inspect session/virtual-device state and recent events |
| `/touch` / `/collision` / `/battery 10` | Exercise simulated sensor and battery behavior |
| `/quit` | Exit |

Natural affirmative/negative replies can resolve a pending memory. Ambiguous replies should not be treated as blanket approval. `/reset yes` is destructive: it clears stored memories, pending proposals and growth state; do not use it for routine demonstrations.

## Cancellation and troubleshooting

- **Ctrl+C during generation:** discard the unfinished response rather than committing it to history/growth.
- **Ctrl+C during speech playback:** stop playback; preserve the already completed text response and growth record.
- **Rules provider instead of local:** inspect `/model`, check LM Studio's server and loaded model identifier.
- **Recording ends too early:** try `/pause 3` or `/endpoint off`.
- **Wrong microphone:** list devices with `.\.venv\Scripts\python.exe -m sounddevice`, set `PET_YAYA_MIC_DEVICE` to the input device number, then restart.
- **Slow first recognition:** model loading can make a cold request slower. Measure cold and warm timings separately.
- **GPU load failure:** retry recognition with `PET_YAYA_STT_DEVICE=cpu`; configure dialogue-model offload separately in LM Studio.

Runtime memory and growth data are created in `software/data/pet_yaya.db`. Speech models reside under `software/models/`. Neither belongs in the repository.
