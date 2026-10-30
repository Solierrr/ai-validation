from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler

from src.workflow.observability.llm_dedupe import DuplicateRuns


class PromptOverride(AsyncCallbackHandler):
    run_inline = True

    def __init__(
        self,
        node: str,
        overrides: dict[int, dict[int, str]],
        *,
        types: tuple[str, ...] = ("system",),
        repeat_first: bool = False,
    ) -> None:
        self.node = node
        self.overrides = overrides
        self.types = types
        self.repeat_first = repeat_first
        self.calls = 0
        self.applied = 0
        self._dedupe = DuplicateRuns()

    async def on_llm_end(self, response, *, run_id, **kwargs: Any):
        self._dedupe.finish(run_id)

    async def on_llm_error(self, error, *, run_id, **kwargs: Any):
        self._dedupe.finish(run_id)

    async def on_chat_model_start(
        self, serialized, messages, *, run_id, metadata=None, **kwargs: Any
    ):
        if (metadata or {}).get("langgraph_node") != self.node:
            return
        if self._dedupe.start(run_id, self.node, messages):
            return
        call, self.calls = self.calls, self.calls + 1
        wanted = self.overrides.get(call)
        if not wanted and self.repeat_first:
            wanted = self.overrides.get(0)
        if not wanted:
            return
        for group in messages:
            for position, new_text in wanted.items():
                editable = position < len(group) and group[position].type in self.types
                if editable and group[position].content != new_text:
                    group[position].content = new_text
                    self.applied += 1
