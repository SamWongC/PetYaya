# GitLab preparation checklist

## What this package contains

This folder contains a standalone source snapshot with English documentation, source code, tests, launch scripts and dependency manifests. Personal runtime data, audio recordings, model downloads and virtual environments are excluded. The original development directory remains unchanged. No Git repository was initialized and nothing was uploaded during preparation.

The repository layout is already assembled:

```text
repository-root/
├── README.md                    English README from this package
├── PROJECT_STRUCTURE.md
├── RUNNING.md
├── TESTING.md
├── ROADMAP.md
├── GITLAB_PREPARATION.md
├── .gitignore                   Reviewed project ignore rules
├── docs/                        Existing architecture documentation
└── software/                    Reviewed source, scripts and tests only
```

The original machine-specific Chinese README is not distributed. An early Chinese architecture reference is retained under `docs/architecture/`; the English root documents describe current behavior. Test fixtures use a generic example name rather than the developer's personal name. This is a snapshot, not an automatically synchronized mirror of the development directory.

## Exclude private and machine-specific artifacts

- `software/data/`: SQLite files, pending/confirmed memories and temporary audio.
- `.venv/`, Python caches, generated build/package metadata and tool caches.
- `software/models/`, downloaded model weights and model caches.
- `.env` and private environment variants, credentials, tokens and authentication configuration.
- Personal screenshots, terminal captures, benchmark inputs containing personal speech, and unreviewed logs.

The included `.gitignore` excludes virtual environments, runtime data, models, environment files, database files, audio and common caches. These rules are a safeguard, not a comprehensive secret detector. Ignore rules do not remove files already tracked in Git or erase earlier commits.

## Before the first push

1. Choose the exact repository root and visibility. Do not publish the entire parent workspace or `Info` directory, which contain unrelated personal material.
2. Review all files intended for staging. Copy only source, tests, necessary scripts and reviewed documentation into a clean staging directory if helpful.
3. Run the automated tests and record the result. Do not invent screenshots or benchmark results to make the repository appear more complete.
4. Inspect staged filenames and diffs using `git status --short`, `git diff --cached --stat`, and `git diff --cached`. Check for secrets, personal facts and machine-specific paths.
5. Review third-party dependency and model licenses. No project license was selected or added by this documentation task; do not label the repository open source without an appropriate license decision.
6. Confirm the GitLab destination and visibility before pushing. Repository creation, remote configuration, CI execution and upload are separate follow-up actions.

## Suggested presentation emphasis

Present the work as an engineering prototype with working integration and regression tests: local dialogue, speech input/output, consent-gated memory, persistent state, cancellation and safety boundaries. Distinguish these implemented mechanisms from planned hardware, autonomous behavior and formal performance evaluation.
