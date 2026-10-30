from typing import Any


class DuplicateRuns:
    def __init__(self) -> None:
        self._open: dict[tuple, Any] = {}
        self._keys: dict[Any, tuple] = {}
        self._duplicates: set[Any] = set()

    def start(self, run_id: Any, node: str | None, messages: list[list]) -> bool:
        key = (node, tuple(id(m) for group in messages for m in group))
        if key in self._open:
            self._duplicates.add(run_id)
            return True
        self._open[key] = run_id
        self._keys[run_id] = key
        return False

    def finish(self, run_id: Any) -> bool:
        if run_id in self._duplicates:
            self._duplicates.discard(run_id)
            return True
        key = self._keys.pop(run_id, None)
        if key is not None:
            self._open.pop(key, None)
        return False
