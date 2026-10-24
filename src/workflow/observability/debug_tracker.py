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

MAX_FIELD_CHARS = 4000
MAX_TOTAL_BYTES = 256 * 1024
_FIELD_LIMITS = (MAX_FIELD_CHARS, 1000, 250, 80)
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


def mask_pii(text: str) -> str:
    text = _DATA_URI.sub(_IMAGE_OMITTED, text)
    text = _URL_QUERY.sub(r"\1?[omitido]", text)
    for kind, pattern in PII_PATTERNS:
        text = re.sub(pattern, f"[{kind}]", text)
    return text


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


class DebugTracker(AsyncCallbackHandler):
    """Acumula, em memória e durante um turno, o que cada nó recebeu e devolveu."""

    def __init__(self) -> None:
        self._nodes: list[dict[str, Any]] = []
        self._by_run: dict[Any, dict[str, Any]] = {}
        self._open_by_name: dict[str, dict[str, Any]] = {}
        self._starts: dict[Any, float] = {}
        self._llm_runs: dict[Any, dict[str, Any]] = {}
        self._orphan_llm: list[dict[str, Any]] = []
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
            "error": None,
        }
        self._nodes.append(record)
        self._by_run[run_id] = record
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
        self._finish_llm(run_id, {"error": f"{type(error).__name__}: {error}"})

    # --- resultado --------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """Estrutura final, anonimizada e dentro do teto de tamanho."""
        nodes = [dict(record) for record in self._nodes]
        for limit in _FIELD_LIMITS:
            clipper = _Clipper(limit)
            body = {
                "nodes": clipper.clean(nodes),
                "llm_calls_outside_nodes": clipper.clean(self._orphan_llm),
            }
            size = len(json.dumps(body, ensure_ascii=False, default=str).encode())
            if size <= MAX_TOTAL_BYTES:
                break
        if size > MAX_TOTAL_BYTES:
            for node in body["nodes"]:
                node["input"] = None
                for call in node["llm_calls"]:
                    call["prompt"] = None
            body["llm_calls_outside_nodes"] = []
        body["truncated"] = clipper.clipped or size > MAX_TOTAL_BYTES
        body["duration_ms"] = round((time.perf_counter() - self.started_at) * 1000, 1)
        return body
