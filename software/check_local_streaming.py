"""Exercise real local SSE, cancellation and recovery without personal data."""

import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent / "src"))

from pet_yaya.adapters.simulator import ConsoleActuator
from pet_yaya.bootstrap import build_simulator
from pet_yaya.config import DialogueSettings
from pet_yaya.domain.cancellation import CancellationToken, DialogueCancelled


def main():
    with TemporaryDirectory(prefix="yaya-stream-check-") as folder:
        console = ConsoleActuator()
        yaya = build_simulator(
            database_path=Path(folder) / "test.db", actuator=console,
            dialogue_settings=DialogueSettings(mode="local", timeout_seconds=60),
        )
        started = time.monotonic()
        times = []
        def preview(chunk):
            times.append(time.monotonic() - started)
            console.preview(chunk)

        print("1. Complete real streamed reply", flush=True)
        result = yaya.interact("用三句话讲一个小兔子看星星的故事。", on_text=preview)
        assert yaya.dialogue_status().active_provider == "local", yaya.dialogue_status().last_error
        assert len(times) > 1, "No incremental text was received"
        assert not result.pending_memory_id
        print(f"chunks={len(times)} first={times[0]:.2f}s total={time.monotonic() - started:.2f}s", flush=True)

        print("2. Cancel after first text chunk", flush=True)
        growth_before = yaya.growth_state().interaction_count
        history_before = tuple(yaya._recent_turns)
        token = CancellationToken()
        def cancel_preview(chunk):
            console.preview(chunk)
            token.cancel()
        started = time.monotonic()
        try:
            yaya.interact("用十句话讲一个太空旅行故事。", on_text=cancel_preview, cancellation=token)
        except DialogueCancelled:
            console.abort_preview()
        else:
            raise AssertionError("Reply was not cancelled")
        assert yaya.growth_state().interaction_count == growth_before
        assert tuple(yaya._recent_turns) == history_before
        assert not yaya.list_memories()
        assert yaya.session_status().state.value == "idle"
        print(f"cancelled; growth/history unchanged; elapsed={time.monotonic() - started:.2f}s", flush=True)

        print("3. Next turn after cancellation", flush=True)
        yaya.interact("你好，请用一句话打个招呼。", on_text=console.preview)
        assert yaya.dialogue_status().active_provider == "local", yaya.dialogue_status().last_error
        assert yaya.growth_state().interaction_count == growth_before + 1
        yaya.shutdown()
        print("PASS: stream, cancel and recovery", flush=True)


if __name__ == "__main__":
    main()

