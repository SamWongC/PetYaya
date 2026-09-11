"""Live identity regression probe using synthetic memories; no database writes."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from pet_yaya.adapters.openai_dialogue import LMStudioChatDialogueEngine
from pet_yaya.domain.models import ConfirmedMemory, DialogueContext, MemoryCandidate


def main() -> None:
    engine = LMStudioChatDialogueEngine(
        api_key=os.getenv("PET_YAYA_LOCAL_API_TOKEN", "lm-studio"),
        model=os.getenv("PET_YAYA_LOCAL_MODEL", "qwen/qwen3.5-9b"),
        base_url=os.getenv("PET_YAYA_LOCAL_BASE_URL", "http://127.0.0.1:1234/v1"),
        timeout_seconds=60,
    )
    memories = tuple(
        ConfirmedMemory.from_candidate(MemoryCandidate(
            category="profile", content=text, source="explicit_user_request"
        )) for text in ("我的名字是小林", "我是你的开发者")
    )
    for question in ("我是谁", "你是谁", "谁是你的开发者", "我叫什么名字"):
        reply = engine.respond(question, DialogueContext(memories, 2, ()))
        print(f"问：{question}\n答：{reply.speech}\n记忆候选：{reply.memory_candidate}", flush=True)
    reply = engine.respond("我叫什么名字", DialogueContext((), 0, ()))
    print(f"无记忆时询问名字：{reply.speech}", flush=True)


if __name__ == "__main__":
    main()

