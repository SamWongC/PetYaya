# Project structure and architecture

## Source layout

The following describes this repository. Runtime directories are created locally and are not distributed.

```text
PetYaya/
├── README.md                         English project overview
├── PROJECT_STRUCTURE.md              Architecture and source layout
├── RUNNING.md                        Setup and execution
├── TESTING.md                        Verification and demonstration
├── ROADMAP.md                        Planned work
├── GITLAB_PREPARATION.md              Publication checklist
├── .gitignore
├── docs/
│   └── architecture/
│       └── software_architecture.md
└── software/
    ├── pyproject.toml                Metadata; Python >= 3.11
    ├── launch_simulator.py           CLI entry and optional LM Studio startup
    ├── run_simulator.cmd             Windows console launcher
    ├── run_local_simulator.cmd       Local-model launcher
    ├── run_voice_simulator.cmd       Local-model + voice launcher
    ├── requirements-voice.txt
    ├── requirements-voice-gpu.txt
    ├── setup_voice.py                Download optional speech models
    ├── check_*.py                    Integration/smoke checks
    ├── benchmark_voice.py            Recognition timing utility
    ├── src/pet_yaya/
    │   ├── main.py                  Interactive commands and voice workflow
    │   ├── bootstrap.py             Dependency wiring and SQLite setup
    │   ├── config.py                Environment-based model settings
    │   ├── domain/                  Models, growth, events, cancellation,
    │   │                            memory intent, speech endpoint logic
    │   ├── application/             Orchestrator and session manager
    │   ├── ports/                   Interfaces for external dependencies
    │   ├── adapters/                Model transport, simulator, voice,
    │   │                            recognition worker, VAD and Windows TTS
    │   └── infrastructure/          SQLite and in-memory repositories
    ├── tests/                       Automated unit/regression suite
    ├── data/                        Runtime state; excluded from Git
    ├── models/                      Downloaded speech models; excluded
    └── .venv/                       Local Python environment; excluded
```

## Component responsibilities

The Chinese document in `docs/architecture/` is preserved as an early design reference. This English guide describes the current prototype; historical milestones should not be read as current implementation status.

| Component | Responsibility |
| --- | --- |
| `main.py` | Accept commands or speech input, display streaming previews, coordinate playback and confirmation |
| `application/orchestrator.py` | Coordinate dialogue, memory proposals, action safety, growth updates and completed-turn history |
| `application/session_manager.py` | Track interaction state and virtual-device events |
| `domain/` | Keep deterministic rules and value types independent of model servers and microphones |
| `ports/contracts.py` | Define contracts for dialogue, actuation, safety and persistence |
| `adapters/openai_dialogue.py` | Shared structured-output parsing, local LM Studio adapter, optional remote adapter and fallback routing |
| `adapters/voice.py` and speech-worker modules | Capture audio, invoke local recognition, manage cancellation and Windows playback |
| `infrastructure/sqlite.py` | Persist confirmed/pending memory and growth state |
| `bootstrap.py` | Assemble concrete implementations for the simulator |

## Interaction flow

```text
Typed input OR microphone -> endpoint detection -> local transcription
                               |
                               v
                     Command / intent handling
                               |
                               v
                    Application orchestrator
                       /                \
              Memory workflow       Dialogue adapter
              + approval gate       + text preview
                       \                /
                        Validate result
                               |
                 Apply action safety policy
                               |
              Persist completed interaction state
                               |
               Console output -> optional speech
```

The microphone path uses endpoint detection before transcription. Text previews are not committed conversation turns. A cancelled or incomplete model response must not be treated as a completed interaction.

## Design decisions

1. **Hardware-independent core.** Actuation is currently a console adapter. Future robot drivers should implement the relevant ports instead of putting device logic inside dialogue code.
2. **Explicit memory approval.** A proposed memory and a confirmed memory are distinct states. Model output alone does not authorize long-term storage.
3. **Bounded context.** Short-term dialogue uses a limited recent-turn window; confirmed memory is persisted separately. This is not an unlimited transcript archive or a vector retrieval system.
4. **Safe presentation fallback.** An invalid intensity for a recognized action becomes `idle` with intensity `0`; valid speech can finish. Unknown action names and invalid memory payloads remain rejected by model-result parsing.
5. **Observable degradation.** `/model`, `/status`, and `/events` expose provider and session information for debugging.
6. **Explainable growth.** Each completed interaction adds one interaction and growth point. Thresholds at 3, 8 and 15 unlock named identifiers. These are not separately validated learned capabilities or an implemented weekly reporting scheduler.

## Hardware boundary

Future integration requires concrete actuator/sensor adapters, device configuration, timing and failure handling, and an independent physical safety layer. Existing collision and low-battery behavior only simulates these conditions. Changing an adapter is an architectural extension point, not evidence that the system is ready to control a physical robot safely.
