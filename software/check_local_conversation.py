"""Real local conversation probe in an isolated temporary database."""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent / "src"))
from pet_yaya.bootstrap import build_simulator
from pet_yaya.config import DialogueSettings


def main():
    with TemporaryDirectory(prefix="yaya-conversation-") as folder:
        yaya = build_simulator(
            database_path=Path(folder) / "test.db",
            dialogue_settings=DialogueSettings(mode="local", timeout_seconds=60),
        )
        for question in ("请介绍一下什么是开发者", "可不可以说得更学术一点", "请把刚才的回答再说简单一点"):
            print(f"问：{question}", flush=True)
            result = yaya.interact(question)
            assert yaya.dialogue_status().active_provider == "local", yaya.dialogue_status().last_error
            if result.pending_memory_id:
                yaya.confirm_memory(result.pending_memory_id, False)
        assert not yaya.list_memories()
        yaya.shutdown()


if __name__ == "__main__":
    main()

