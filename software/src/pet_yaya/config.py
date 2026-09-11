from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DialogueSettings:
    mode: str = "auto"
    model: str = "gpt-5.6"
    api_key: str | None = None
    base_url: str = "https://api.openai.com/v1"
    local_model: str = "qwen/qwen3.5-9b"
    local_base_url: str = "http://127.0.0.1:1234/v1"
    local_api_token: str = "lm-studio"
    timeout_seconds: float = 20.0
    safety_identifier: str | None = None

    @classmethod
    def from_env(
        cls, environ: Mapping[str, str] | None = None
    ) -> "DialogueSettings":
        values = os.environ if environ is None else environ
        mode = values.get("PET_YAYA_DIALOGUE_MODE", "auto").strip().lower()
        if mode not in {"auto", "openai", "local", "rules"}:
            mode = "auto"

        api_key = values.get("OPENAI_API_KEY", "").strip() or None
        model = values.get("PET_YAYA_OPENAI_MODEL", "gpt-5.6").strip()
        base_url = values.get(
            "PET_YAYA_OPENAI_BASE_URL", "https://api.openai.com/v1"
        ).strip()
        local_model = values.get(
            "PET_YAYA_LOCAL_MODEL", "qwen/qwen3.5-9b"
        ).strip()
        local_base_url = values.get(
            "PET_YAYA_LOCAL_BASE_URL", "http://127.0.0.1:1234/v1"
        ).strip()
        local_api_token = values.get(
            "PET_YAYA_LOCAL_API_TOKEN", "lm-studio"
        ).strip()
        safety_identifier = (
            values.get("PET_YAYA_SAFETY_IDENTIFIER", "").strip() or None
        )
        try:
            timeout = float(
                values.get("PET_YAYA_OPENAI_TIMEOUT_SECONDS", "20")
            )
        except ValueError:
            timeout = 20.0

        return cls(
            mode=mode,
            model=model or "gpt-5.6",
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            local_model=local_model or "qwen/qwen3.5-9b",
            local_base_url=local_base_url.rstrip("/"),
            local_api_token=local_api_token or "lm-studio",
            timeout_seconds=max(1.0, min(timeout, 120.0)),
            safety_identifier=safety_identifier,
        )

