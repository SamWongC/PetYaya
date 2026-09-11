# Roadmap

This roadmap is proposed work, not an implementation or delivery-date commitment. The current baseline is a working desktop conversation and voice prototype with persistence and 122 passing automated tests.

## 1. Cancellable sentence-level speech output

**Goal:** start speaking earlier instead of waiting for the entire response.

- Introduce sentence segmentation and a bounded speech queue.
- Keep text preview, speech playback and committed conversation state distinct.
- Cancel queued audio when a turn is interrupted or becomes invalid.
- Decide explicitly how to handle text already spoken before final structured-output validation; speech cannot be retracted.

**Acceptance:** no duplicated/reordered sentences, no stale audio leaking into the next turn, prompt cancellation, unchanged memory-approval safeguards, and measured improvement in time to first audible response.

## 2. More natural multi-turn voice interaction

**Goal:** reduce repeated keyboard interaction without unintentionally enabling continuous recording.

- Add an explicit, user-controlled conversation mode with clear listening/processing/speaking indicators.
- Define inactivity timeout and reliable stop/mute controls.
- Evaluate echo handling before attempting speech interruption during playback.

**Acceptance:** no self-triggering on Yaya's own speaker output, predictable exit behavior, and no recording outside the user-selected mode. Wake-word and full-duplex support remain separate design tasks.

## 3. Reproducible evaluation and packaging

**Goal:** make results repeatable on another developer's machine.

- Add documented cold/warm latency measurements and a representative speech test set.
- Measure false memory acceptance as well as recognition accuracy.
- Validate installation on a clean Windows environment; record tested dependency/model versions.
- Add GitLab CI for model-free tests. Keep GPU, microphone and model-download jobs optional.
- Select an appropriate license after reviewing third-party code and model distribution terms.

**Acceptance:** a new developer can run the rules-only demo and tests without private paths, credentials or downloaded model weights in Git.

## 4. Memory and privacy hardening

**Goal:** make persistence easier to inspect and safer to operate.

- Add explicit correction/expiry policies and a privacy-oriented review of pending state.
- Review sensitive-content handling and ambiguous consent with adversarial examples.
- Design export/deletion behavior and document what remains in backups or logs.

**Acceptance:** tests demonstrate that ambiguous consent does not silently create long-term memory; users can inspect and remove stored facts. Do not claim production privacy compliance solely from passing unit tests.

## 5. Hardware integration, after software validation

**Goal:** connect a small physical prototype without coupling device control to model output.

- Choose compute placement: onboard inference, a nearby computer, or a hybrid arrangement.
- Implement actuator and sensor adapters with explicit limits and timeouts.
- Add an independent emergency stop and power/motion safety checks.
- Test one low-risk action at a time before expanding movement capability.

**Acceptance:** documented hardware configuration, bench-test evidence, safe disconnect/failure behavior, and measured timing. Navigation, vision and unsupervised household use are outside the current baseline.
