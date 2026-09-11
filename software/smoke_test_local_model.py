from __future__ import annotations

import os
import json
import sys
from pathlib import Path
from collections.abc import Mapping

sys.path.insert(0, str(Path(__file__).parent / "src"))

from pet_yaya.adapters.openai_dialogue import (  # noqa: E402
    DialogueServiceError,
    LMStudioChatDialogueEngine,
    UrllibJsonTransport,
)
from pet_yaya.domain.models import DialogueContext  # noqa: E402


class CapturingTransport:
    def __init__(self) -> None:
        self.response: Mapping[str, object] | None = None
        self._transport = UrllibJsonTransport()

    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        timeout_seconds: float,
    ) -> Mapping[str, object]:
        self.response = self._transport.post_json(
            url, headers, payload, timeout_seconds
        )
        return self.response


def main() -> None:
    base_url = os.getenv(
        "PET_YAYA_LOCAL_BASE_URL", "http://127.0.0.1:1234/v1"
    )
    model = os.getenv("PET_YAYA_LOCAL_MODEL", "qwen/qwen3.5-9b")
    transport = CapturingTransport()
    engine = LMStudioChatDialogueEngine(
        api_key=os.getenv("PET_YAYA_LOCAL_API_TOKEN", "lm-studio"),
        model=model,
        base_url=base_url,
        timeout_seconds=180,
        transport=transport,
    )
    context = DialogueContext(
        memories=(),
        interaction_count=0,
        unlocked_skills=(),
    )
    try:
        result = engine.respond("你好，请用两句话介绍你自己。", context)
    except DialogueServiceError:
        if transport.response is not None:
            print(
                "raw_response="
                + json.dumps(transport.response, ensure_ascii=False)
            )
        raise
    print(f"model={model}")
    print(f"speech={result.speech}")
    print(f"emotion={result.emotion.value}")
    print(f"action={result.action.name.value}")
    print(f"memory={result.memory_candidate}")


if __name__ == "__main__":
    main()

