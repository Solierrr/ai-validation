import logging
from uuid import uuid4

from src.workflow.observability.prompt_override import PromptOverride

logger = logging.getLogger(__name__)

START = "__start__"
MAX_HISTORY = 2000

REPLAY_BLOCKED_NODES: dict[str, str] = {}


class ReplayError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


async def _turns(workflow, thread_id: str) -> list[list]:
    config = {"configurable": {"thread_id": thread_id}}
    history = []
    async for snapshot in workflow.aget_state_history(config):
        history.append(snapshot)
        if len(history) >= MAX_HISTORY:
            break
    turns: list[list] = []
    for snapshot in reversed(history):
        if snapshot.next == (START,) or not turns:
            turns.append([])
        turns[-1].append(snapshot)
    return turns


async def count_turns(workflow, thread_id: str) -> int:
    return len(await _turns(workflow, thread_id))


def check_replayable(node: str) -> None:
    reason = REPLAY_BLOCKED_NODES.get(node)
    if reason:
        raise ReplayError(422, reason)


async def run_single_node(
    workflow,
    thread_id: str,
    *,
    turn: int,
    node: str,
    occurrence: int,
    overrides: dict[int, dict[int, str]],
    callbacks: list,
    metadata: dict,
    tags: list[str],
    override_types: tuple[str, ...] = ("system",),
):
    check_replayable(node)
    turns = await _turns(workflow, thread_id)
    if turn >= len(turns):
        raise ReplayError(404, "Esse run não existe mais no histórico de debug.")
    snapshots = turns[turn]
    candidates = [
        index for index, snapshot in enumerate(snapshots) if snapshot.next == (node,)
    ]
    if occurrence >= len(candidates):
        raise ReplayError(404, f"O nó {node} não rodou {occurrence + 1}x neste turno.")
    index = candidates[occurrence]
    target = snapshots[index]
    previous = snapshots[index - 1] if index > 0 else None
    if previous is None or len(previous.next) != 1:
        raise ReplayError(
            409, "Não foi possível reconstruir o ponto de entrada deste nó."
        )

    copy_id = f"{thread_id}:replay:{uuid4().hex[:8]}"
    copy_config = {"configurable": {"thread_id": copy_id}}
    override = PromptOverride(node, overrides, types=override_types, repeat_first=True)
    try:
        await workflow.aupdate_state(
            copy_config, target.values, as_node=previous.next[0]
        )
        restored = await workflow.aget_state(copy_config)
        if restored.next != (node,):
            raise ReplayError(
                409,
                "O estado reconstruído não leva a este nó; a execução foi cancelada.",
            )
        state = await workflow.ainvoke(
            None,
            {
                **copy_config,
                "callbacks": [override, *callbacks],
                "metadata": metadata,
                "tags": tags,
            },
            interrupt_after=[node],
        )
        after = await workflow.aget_state(copy_config)
        return state, tuple(after.next), override.applied
    finally:
        try:
            await workflow.checkpointer.adelete_thread(copy_id)
        except Exception:
            logger.warning(
                "Falha ao apagar a thread de replay %s", copy_id, exc_info=True
            )
