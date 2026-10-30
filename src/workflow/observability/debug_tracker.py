"""Coletor do modo debug: entrada e saída de cada nó do grafo e de cada chamada de LLM.

Só é usado pelas rotas `/debug/*`. O conteúdo é anonimizado (CPF, CNPJ, telefone e
e-mail) e limitado em tamanho antes de sair. Imagem em base64 nunca sai (vira
`[imagem omitida]`) e a query string de URL assinada é removida."""

import json
import re
import time
from datetime import UTC, datetime
from typing import Any

from ai_lib.guardrails.anonymize import PII_PATTERNS
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from src.workflow.observability.llm_dedupe import DuplicateRuns

MAX_FIELD_CHARS = 4000
_CLIP_MARGIN = 256

# Chaves do estado do grafo que valem a pena na entrada de um nó.
_INPUT_KEYS = (
    "cert_nr10_url",
    "cert_nr35_url",
    "current_date",
    "is_safe",
    "security_error_code",
    "nr10_result",
    "nr35_result",
)
_IMAGE_KEYS = frozenset({"cert_nr10_b64", "cert_nr35_b64"})
_IMAGE_OMITTED = "[imagem omitida]"
_DATA_URI = re.compile(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=_-]+")
_URL_QUERY = re.compile(r"(https?://[^\s\"'<>?#]+)[?#][^\s\"'<>]*")


def _message_text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        content = [
            {**part, "image_url": _IMAGE_OMITTED}
            if isinstance(part, dict) and "image_url" in part
            else part
            for part in content
        ]
    return json.dumps(content, ensure_ascii=False, default=str)


def _jsonable(value: Any, depth: int = 0) -> Any:
    """Converte mensagens do LangChain e demais objetos em estruturas JSON."""
    if depth > 6:
        return "..."
    if isinstance(value, BaseMessage):
        return {"type": value.type, "content": _message_text(value)}
    if isinstance(value, BaseModel):
        return _jsonable(value.model_dump(mode="json"), depth + 1)
    if isinstance(value, dict):
        return {
            str(key): (
                (_IMAGE_OMITTED if item else None)
                if str(key) in _IMAGE_KEYS
                else _jsonable(item, depth + 1)
            )
            for key, item in value.items()
        }
    if isinstance(value, list | tuple | set | frozenset):
        return [_jsonable(item, depth + 1) for item in value]
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return repr(value)


def _node_input(inputs: Any) -> Any:
    if not isinstance(inputs, dict):
        return _jsonable(inputs)
    return {key: _jsonable(inputs[key]) for key in _INPUT_KEYS if key in inputs}


def _prompt_messages(messages: list[BaseMessage]) -> list[dict[str, str]]:
    return [_jsonable(message) for message in messages]


_EMAIL_LINEAR = r"[a-zA-Z0-9_.+-]{1,64}@[a-zA-Z0-9-]{1,255}\.[a-zA-Z0-9-.]{1,255}"


def mask_pii(text: str) -> str:
    text = _DATA_URI.sub(_IMAGE_OMITTED, text)
    text = _URL_QUERY.sub(r"\1?[omitido]", text)
    for kind, pattern in PII_PATTERNS:
        if kind == "EMAIL":
            pattern = _EMAIL_LINEAR
        text = re.sub(pattern, f"[{kind}]", text)
    return text


def _whole(value: Any) -> Any:
    if isinstance(value, str):
        return mask_pii(value)
    if isinstance(value, dict):
        return {key: _whole(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_whole(item) for item in value]
    return value


class _Clipper:
    """Anonimiza e corta as strings de uma estrutura, lembrando se cortou algo."""

    def __init__(self, limit: int):
        self.limit = limit
        self.clipped = False

    def clean(self, value: Any) -> Any:
        if isinstance(value, str):
            too_long = len(value) > self.limit
            value = mask_pii(value[: self.limit + _CLIP_MARGIN])
            if too_long or len(value) > self.limit:
                self.clipped = True
                return value[: self.limit] + "…"
            return value
        if isinstance(value, dict):
            return {key: self.clean(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.clean(item) for item in value]
        return value


def _clean_editable_message(message: Any, clipper: _Clipper) -> tuple[Any, bool]:
    content = message["content"]
    if not isinstance(content, str):
        return {**message, "editable": False}, False
    text = mask_pii(content)
    complete = text == content
    if not complete:
        clipper.clipped = True
    return {
        **message,
        "content": text,
        "editable": complete,
    }, complete


def _clean_call(
    call: dict[str, Any], clipper: _Clipper, editable_types: tuple[str, ...]
) -> dict[str, Any]:
    prompt = call.get("prompt")
    rest = {key: clipper.clean(value) for key, value in call.items() if key != "prompt"}
    if not isinstance(prompt, list):
        return {**rest, "prompt": _whole(prompt), "prompt_complete": False}
    cleaned, complete = [], True
    for message in prompt:
        if isinstance(message, dict) and message.get("type") in editable_types:
            kept, whole = _clean_editable_message(message, clipper)
            cleaned.append(kept)
            complete = complete and whole
        else:
            item = _whole(message)
            cleaned.append(
                {**item, "editable": False} if isinstance(item, dict) else item
            )
    return {**rest, "prompt": cleaned, "prompt_complete": complete}


def _clean_node(
    node: dict[str, Any], clipper: _Clipper, editable_types: tuple[str, ...]
) -> dict[str, Any]:
    cleaned = {
        key: clipper.clean(value) for key, value in node.items() if key != "llm_calls"
    }
    cleaned["llm_calls"] = [
        _clean_call(call, clipper, editable_types) for call in node["llm_calls"]
    ]
    return cleaned


def _usage(response: Any) -> tuple[int | None, int | None, str | None]:
    """Tokens e modelo de uma resposta de LLM; qualquer um pode faltar."""
    tokens_in = tokens_out = None
    try:
        message = getattr(response.generations[0][0], "message", None)
    except (AttributeError, IndexError):
        message = None
    usage = getattr(message, "usage_metadata", None) if message else None
    meta = getattr(message, "response_metadata", None) or {}
    if usage:
        tokens_in = usage.get("input_tokens")
        tokens_out = usage.get("output_tokens")
    llm_output = getattr(response, "llm_output", None) or {}
    token_usage = llm_output.get("token_usage") or {}
    if tokens_in is None:
        tokens_in = token_usage.get("prompt_tokens")
    if tokens_out is None:
        tokens_out = token_usage.get("completion_tokens")
    model = meta.get("model_name") or meta.get("model") or llm_output.get("model_name")
    return tokens_in, tokens_out, model


def _completion_text(response: Any) -> str:
    try:
        generation = response.generations[0][0]
    except (AttributeError, IndexError):
        return ""
    message = getattr(generation, "message", None)
    if message is not None:
        text = _message_text(message)
        tool_calls = getattr(message, "tool_calls", None)
        if not text and tool_calls:
            return json.dumps(
                [call.get("args") for call in tool_calls],
                ensure_ascii=False,
                default=str,
            )
        return text
    return str(getattr(generation, "text", ""))


def _tool_output(output: Any) -> Any:
    if isinstance(output, BaseMessage):
        return _message_text(output)
    return _jsonable(output)


def _tool_spec(tool: Any) -> dict[str, str] | None:
    if not isinstance(tool, dict):
        return None
    spec = tool.get("function") if isinstance(tool.get("function"), dict) else tool
    name = spec.get("name")
    if not isinstance(name, str) or not name:
        return None
    description = spec.get("description")
    return {
        "name": name,
        "description": description if isinstance(description, str) else "",
    }


def _available_tools(kwargs: dict[str, Any]) -> list[dict[str, str]]:
    params = kwargs.get("invocation_params") or {}
    raw = params.get("tools") or params.get("functions") or []
    found: list[dict[str, str]] = []
    for item in raw if isinstance(raw, list) else []:
        group = item.get("function_declarations") if isinstance(item, dict) else None
        for tool in group if isinstance(group, list) else [item]:
            spec = _tool_spec(tool)
            if spec:
                found.append(spec)
    return found


class DebugTracker(AsyncCallbackHandler):
    """Acumula, em memória e durante um turno, o que cada nó recebeu e devolveu."""

    def __init__(self, editable_types: tuple[str, ...] = ("system",)) -> None:
        self.editable_types = editable_types
        self._dedupe = DuplicateRuns()
        self._nodes: list[dict[str, Any]] = []
        self._by_run: dict[Any, dict[str, Any]] = {}
        self._open_by_name: dict[str, dict[str, Any]] = {}
        self._starts: dict[Any, float] = {}
        self._llm_runs: dict[Any, dict[str, Any]] = {}
        self._orphan_llm: list[dict[str, Any]] = []
        self._tool_runs: dict[Any, dict[str, Any]] = {}
        self._orphan_tools: list[dict[str, Any]] = []
        self._parent_of: dict[Any, Any] = {}
        self._record_of: dict[Any, dict[str, Any]] = {}
        self.started_at = time.perf_counter()

    # --- nós do grafo -----------------------------------------------------
    @staticmethod
    def _is_node_run(name: str | None, metadata: dict | None) -> bool:
        node = (metadata or {}).get("langgraph_node")
        return bool(node) and name == node

    async def on_chain_start(
        self,
        serialized,
        inputs,
        *,
        run_id,
        parent_run_id=None,
        tags=None,
        metadata=None,
        name=None,
        **kwargs,
    ):
        name = name or (serialized or {}).get("name")
        self._parent_of[run_id] = parent_run_id
        if not self._is_node_run(name, metadata) or name in self._open_by_name:
            return
        record = {
            "order": len(self._nodes) + 1,
            "node": name,
            "started_at": datetime.now(UTC).isoformat(),
            "duration_ms": None,
            "status": "running",
            "input": _node_input(inputs),
            "output": None,
            "llm_calls": [],
            "tools": [],
            "tool_calls": [],
            "error": None,
        }
        self._nodes.append(record)
        self._by_run[run_id] = record
        self._record_of[run_id] = record
        self._open_by_name[name] = record
        self._starts[run_id] = time.perf_counter()

    def _close(self, run_id, status, output=None, error=None):
        record = self._by_run.pop(run_id, None)
        if record is None:
            return
        started = self._starts.pop(run_id, time.perf_counter())
        record["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
        record["status"] = status
        record["output"] = _jsonable(output)
        record["error"] = error
        self._open_by_name.pop(record["node"], None)

    async def on_chain_end(self, outputs, *, run_id, **kwargs):
        self._close(run_id, "ok", output=outputs)

    async def on_chain_error(self, error, *, run_id, **kwargs):
        self._close(run_id, "error", error=f"{type(error).__name__}: {error}")

    # --- chamadas de LLM --------------------------------------------------
    def _start_llm(self, run_id, prompt, metadata):
        self._starts[run_id] = time.perf_counter()
        self._llm_runs[run_id] = {
            "node": (metadata or {}).get("langgraph_node"),
            "prompt": prompt,
        }

    async def on_chat_model_start(
        self, serialized, messages, *, run_id, metadata=None, **kwargs
    ):
        node = (metadata or {}).get("langgraph_node")
        self._register_tools(node, kwargs)
        if self._dedupe.start(run_id, node, messages):
            return
        flat = [m for group in messages for m in group]
        self._start_llm(run_id, _prompt_messages(flat), metadata)

    async def on_llm_start(
        self, serialized, prompts, *, run_id, metadata=None, **kwargs
    ):
        self._start_llm(
            run_id, [{"type": "prompt", "content": p} for p in prompts], metadata
        )

    def _finish_llm(self, run_id, extra):
        start = self._llm_runs.pop(run_id, None)
        if start is None:
            return
        started = self._starts.pop(run_id, time.perf_counter())
        call = {
            "model": None,
            "prompt": start["prompt"],
            "completion": None,
            "tokens_in": None,
            "tokens_out": None,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": None,
            **extra,
        }
        record = self._open_by_name.get(start["node"] or "")
        (record["llm_calls"] if record else self._orphan_llm).append(call)

    async def on_llm_end(self, response, *, run_id, **kwargs):
        if self._dedupe.finish(run_id):
            return
        tokens_in, tokens_out, model = _usage(response)
        self._finish_llm(
            run_id,
            {
                "model": model,
                "completion": _completion_text(response),
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
            },
        )

    async def on_llm_error(self, error, *, run_id, **kwargs):
        if self._dedupe.finish(run_id):
            return
        self._finish_llm(run_id, {"error": f"{type(error).__name__}: {error}"})

    # --- tools ------------------------------------------------------------
    def _owners(self, node: str | None, parent_run_id: Any) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        seen: set[Any] = set()
        current = parent_run_id
        while current is not None and current not in seen:
            seen.add(current)
            record = self._record_of.get(current)
            if record is not None and all(record is not other for other in found):
                found.append(record)
            current = self._parent_of.get(current)
        if not found:
            record = self._open_by_name.get(node or "")
            if record is None and self._open_by_name:
                record = next(reversed(self._open_by_name.values()))
            if record is not None:
                found.append(record)
        return found

    def _register_tools(self, node: str | None, kwargs: dict[str, Any]) -> None:
        for record in self._owners(node, kwargs.get("parent_run_id")):
            known = {tool["name"] for tool in record["tools"]}
            for tool in _available_tools(kwargs):
                if tool["name"] not in known:
                    known.add(tool["name"])
                    record["tools"].append(tool)

    async def on_tool_start(
        self, serialized, input_str, *, run_id, metadata=None, inputs=None, **kwargs
    ):
        self._tool_runs[run_id] = {
            "node": (metadata or {}).get("langgraph_node"),
            "name": kwargs.get("name") or (serialized or {}).get("name") or "tool",
            "input": _jsonable(inputs if isinstance(inputs, dict) else input_str),
            "parent": kwargs.get("parent_run_id"),
            "started": time.perf_counter(),
        }

    def _finish_tool(self, run_id, status, output=None, error=None):
        start = self._tool_runs.pop(run_id, None)
        if start is None:
            return
        call = {
            "name": start["name"],
            "input": start["input"],
            "output": output,
            "duration_ms": round((time.perf_counter() - start["started"]) * 1000, 1),
            "status": status,
            "error": error,
        }
        owners = self._owners(start["node"], start["parent"])
        if not owners:
            self._orphan_tools.append(call)
            return
        for record in owners:
            if all(tool["name"] != call["name"] for tool in record["tools"]):
                record["tools"].append({"name": call["name"], "description": ""})
            record["tool_calls"].append(call)

    async def on_tool_end(self, output, *, run_id, **kwargs):
        self._finish_tool(run_id, "ok", output=_tool_output(output))

    async def on_tool_error(self, error, *, run_id, **kwargs):
        self._finish_tool(run_id, "error", error=f"{type(error).__name__}: {error}")

    # --- resultado --------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """Estrutura final, anonimizada e dentro do teto de tamanho."""
        nodes = [dict(record) for record in self._nodes]
        clipper = _Clipper(MAX_FIELD_CHARS)
        body = {
            "nodes": [
                _clean_node(node, clipper, self.editable_types) for node in nodes
            ],
            "llm_calls_outside_nodes": [
                _clean_call(call, clipper, self.editable_types)
                for call in self._orphan_llm
            ],
            "tool_calls_outside_nodes": [
                clipper.clean(call) for call in self._orphan_tools
            ],
        }
        body["truncated"] = clipper.clipped
        body["duration_ms"] = round((time.perf_counter() - self.started_at) * 1000, 1)
        return body
