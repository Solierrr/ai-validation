import time
from dataclasses import dataclass

MAX_RUNS = 5
MAX_AGE_SECONDS = 30 * 60
MAX_BYTES = 64 * 1024 * 1024


@dataclass
class DebugRun:
    sub: str
    run_id: str
    size: int
    created_at: float


def thread_id(sub: str, run_id: str) -> str:
    return f"debug:{sub}:{run_id}"


def estimate_size(state: dict | None) -> int:
    state = state or {}
    return sum(len(state.get(key) or "") for key in ("cert_nr10_b64", "cert_nr35_b64"))


class DebugRunStore:
    def __init__(self, graph) -> None:
        self._graph = graph
        self._runs: dict[tuple[str, str], DebugRun] = {}

    async def _drop(self, run: DebugRun) -> None:
        self._runs.pop((run.sub, run.run_id), None)
        await self._graph.checkpointer.adelete_thread(thread_id(run.sub, run.run_id))

    async def purge(self) -> None:
        limit = time.time() - MAX_AGE_SECONDS
        for run in [r for r in self._runs.values() if r.created_at < limit]:
            await self._drop(run)

    async def add(self, sub: str, run_id: str, size: int) -> None:
        await self.purge()
        self._runs[(sub, run_id)] = DebugRun(sub, run_id, size, time.time())
        while len(self._runs) > 1 and (
            len(self._runs) > MAX_RUNS
            or sum(run.size for run in self._runs.values()) > MAX_BYTES
        ):
            oldest = min(self._runs.values(), key=lambda run: run.created_at)
            if (oldest.sub, oldest.run_id) == (sub, run_id):
                break
            await self._drop(oldest)

    async def exists(self, sub: str, run_id: str) -> bool:
        await self.purge()
        return (sub, run_id) in self._runs
