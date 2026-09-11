"""Real local semantic memory checks with synthetic text and temporary storage."""
from pathlib import Path
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).parent / "src"))
from pet_yaya.bootstrap import build_simulator
from pet_yaya.config import DialogueSettings
from pet_yaya.domain.models import DialogueTurn
from pet_yaya.domain.cancellation import CancellationToken


def main():
    root = Path(__file__).parent / "data" / "voice-temp"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as folder:
        yaya = build_simulator(database_path=Path(folder)/"test.db", dialogue_settings=DialogueSettings(mode="local", timeout_seconds=60))
        try:
            yaya._recent_turns.append(DialogueTurn("我喜欢恐龙", "你喜欢哪种恐龙？"))
            result = yaya.interact("把我的这个爱好记下来")
            assert result.pending_memory_id
            decision = yaya.interpret_confirmation(result.pending_memory_id, "我觉得这件事情值得保存下来", CancellationToken())
            print("Complex consent:", decision)
            assert decision.intent == "approve"
            decision = yaya.interpret_confirmation(result.pending_memory_id, "可以，不过我喜欢三角龙", CancellationToken())
            print("Revision:", decision)
            assert decision.intent == "revise" and "三角龙" in decision.content
            assert not yaya.list_memories()
            decision = yaya.interpret_confirmation(result.pending_memory_id, "可以啊", CancellationToken())
            assert decision.intent == "approve"
            yaya.confirm_memory(result.pending_memory_id, True)
            assert "三角龙" in yaya.list_memories()[0].content
            print("PASS: contextual request, semantic consent, revision, explicit re-approval.")
        finally:
            yaya.shutdown()


if __name__ == "__main__":
    main()

