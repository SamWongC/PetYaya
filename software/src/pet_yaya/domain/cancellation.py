from threading import Event


class DialogueCancelled(RuntimeError):
    """An intentional cancellation, not a model failure."""


class CancellationToken:
    def __init__(self) -> None:
        self._event = Event()

    def cancel(self) -> None:
        self._event.set()

    def check(self) -> None:
        if self._event.is_set():
            raise DialogueCancelled("当前回复已停止。")

