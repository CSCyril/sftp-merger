from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from typing import Any


def run_in_thread(
    root: Any,
    target: Callable[[queue.Queue], Any],
    on_done: Callable[[Any], None],
    on_progress: Callable[[Any], None] | None = None,
    on_error: Callable[[BaseException], None] | None = None,
    on_confirm: Callable[[Any], bool] | None = None,
    poll_ms: int = 100,
) -> threading.Thread:
    q: queue.Queue = queue.Queue()

    def worker() -> None:
        try:
            result = target(q)
            q.put(("done", result))
        except BaseException as exc:
            q.put(("error", exc))

    def poll() -> None:
        try:
            while True:
                kind, payload = q.get_nowait()
                if kind == "progress":
                    if on_progress is not None:
                        on_progress(payload)
                elif kind == "confirm":
                    data, answer_q = payload
                    answer_q.put(on_confirm(data) if on_confirm is not None else False)
                elif kind == "done":
                    on_done(payload)
                    return
                elif kind == "error":
                    if on_error is not None:
                        on_error(payload)
                    else:
                        on_done(payload)
                    return
        except queue.Empty:
            root.after(poll_ms, poll)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    root.after(poll_ms, poll)
    return thread
