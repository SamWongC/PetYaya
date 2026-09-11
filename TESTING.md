# Testing and demonstration

## Latest verified baseline

| Item | Result |
| --- | --- |
| Date | 2026-09-11 |
| Environment | Windows, Python 3.12.14; existing development interpreter used to test this independent source snapshot |
| Command | `python -X utf8 -m unittest discover -s tests -q` |
| Result | 122 tests passed |
| Scope | Existing automated unit/regression suite |

The suite was rerun from this snapshot's `software/` directory: all 122 tests passed with the existing development dependencies available. No virtual environment was copied into this distribution. Generic test names replace personal-name fixtures; application behavior is unchanged. A second run with Python's `-S` option (without site-packages) completed with 5 optional-dependency tests skipped. A rules-only smoke check verified memory proposal, approval and persistence across application instances using a temporary database and this snapshot's own imports.

A fresh-machine installation, live microphone session and live LM Studio integration were not rerun. No coverage percentage or statistically measured speech-accuracy result is claimed.

## Reproduce automated tests

From the source project's `software` directory:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
```

The suite uses isolated/in-memory fixtures and mocked external behavior for relevant paths; it is not a substitute for running a real model or microphone. Do not use the personal runtime database as a test fixture.

## Coverage by responsibility

| Test modules | Main behavior exercised |
| --- | --- |
| `test_orchestrator.py`, `test_session_system.py` | Interaction coordination, virtual-device events, state and safety behavior |
| `test_sqlite_repositories.py` | Repository persistence and memory/growth storage |
| `test_dialogue_history.py`, `test_rewrite.py` | Context handling and response-style follow-ups |
| `test_openai_dialogue.py`, `test_streaming.py` | Model adapter parsing, fallback, stream completion and cancellation |
| `test_memory_intent.py` | Memory-request and confirmation interpretation |
| `test_voice.py`, `test_speech_worker.py`, `test_speech_recognition.py` | Voice workflow, worker behavior and recognition configuration |
| `test_speech_endpoint.py`, `test_recording_endpoint.py` | End-of-speech decisions and recording boundaries |

Recent regressions cover invalid action intensities (out-of-range, missing, non-finite or malformed values): a recognized action becomes `idle` with intensity `0`, while a valid completed reply is retained. Tests also verify that this fallback does not bypass memory validation or approval. Existing incomplete-stream and unknown-action rejection tests remain in place.

## Optional integration checks

Run from `software` after installing the relevant dependencies. Read each script before running it on a new environment.

```powershell
# LM Studio server running and model loaded:
.\.venv\Scripts\python.exe -X utf8 check_local_streaming.py
.\.venv\Scripts\python.exe -X utf8 check_local_identity.py
.\.venv\Scripts\python.exe -X utf8 check_local_conversation.py
.\.venv\Scripts\python.exe -X utf8 check_memory_intent.py

# Windows SAPI and local speech models installed:
.\.venv\Scripts\python.exe -X utf8 check_voice.py --roundtrip
.\.venv\Scripts\python.exe -X utf8 check_voice.py --vocabulary
.\.venv\Scripts\python.exe -X utf8 check_speech_endpoint.py

# Combined synthetic speech and local dialogue:
.\.venv\Scripts\python.exe -X utf8 check_voice.py --dialogue

# Recognition timing:
.\.venv\Scripts\python.exe -X utf8 benchmark_voice.py
```

The speech round-trip checks synthesize input rather than recording a person; `check_voice.py` also inspects the input device configuration. Synthetic speech is useful for regressions but is not representative of accents, children, background noise, or natural hesitation. Passing a vocabulary example does not establish a general word-error rate.

## Five-minute supervisor demonstration

1. Start the local voice simulator. Ask `请用两句话介绍一下你自己` (“Introduce yourself in two sentences”). Check `/model` shows the local provider after the reply.
2. Ask `机器人是什么？`, then `可以讲得更学术一点吗？`, then `更简单一点呢？`. Check the subject remains the same while explanation style changes.
3. Say `请记住，我喜欢恐龙` and approve the proposed content using a natural affirmative reply. Check `/memory` contains the intended fact, not the recognition error you did not approve.
4. Exit and restart. Check `/memory` retains the fact. Explain that this is database persistence, not retraining the model.
5. Request a longer story and press Ctrl+C during generation. Verify the incomplete turn does not increase `/growth`. Complete another turn, then stop its speech playback; verify that completed turn remains recorded.
6. Demonstrate `/battery 10` or `/collision` and explain that these are virtual events, not physical sensor readings.

Use non-personal example facts. If cleaning up, delete only the demonstration memory by its currently displayed number; do not reset the user's database.

## Evaluation to add

Create a fixed, consented test set for common vocabulary, short affirmations, corrections, negation, hesitations and silence. Measure recognition errors, false memory approvals, endpoint truncations, cancellation latency, and time to first audible response. Record hardware, model versions, recording duration, and cold/warm state with each timing. Report distributions rather than presenting a single fast request as typical performance.
