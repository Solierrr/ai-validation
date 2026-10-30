"""Testes do coletor do modo debug (src/workflow/observability/debug_tracker.py)."""

import asyncio
import json
import time
from unittest.mock import patch

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph

from src.workflow.nodes.security_guardrail_node import (
    GuardrailOutput,
    security_guardrail_node,
)
from src.workflow.observability.debug_tracker import DebugTracker, mask_pii
from src.workflow.state import CertificateGraphState

BASE64 = "QUJD" * 5000
SIGNED_URL = "https://bucket.exemplo.com/nr10.jpg?X-Signature=abc123&X-Expires=99"
CPF = "123.456.789-09"


def _fake_structured_llm(**args):
    """LLM falso que responde por tool call, como a saída estruturada real."""
    model = GenericFakeChatModel(
        messages=iter([AIMessage(content="", tool_calls=[{"name": "r", "args": args, "id": "1"}])])
    )
    chain = model | RunnableLambda(lambda msg: GuardrailOutput(**msg.tool_calls[0]["args"]))

    class _Llm:
        def with_structured_output(self, schema):
            return chain

    return _Llm()


def _run_graph(node, state, tracker=None):
    graph = StateGraph(CertificateGraphState)
    graph.add_node("security_guardrail", node)
    graph.add_edge(START, "security_guardrail")
    graph.add_edge("security_guardrail", END)
    tracker = tracker or DebugTracker()
    try:
        asyncio.run(graph.compile().ainvoke(state, config={"callbacks": [tracker]}))
    except Exception:  # noqa: BLE001 - os testes de erro inspecionam o coletor
        pass
    return tracker


def _state():
    return {
        "cert_nr10_url": SIGNED_URL,
        "cert_nr35_url": "https://bucket.exemplo.com/nr35.jpg?X-Signature=abc123",
        "current_date": "2026-07-15",
    }


def test_registra_o_no_real_e_a_chamada_de_llm():
    with (
        patch(
            "src.workflow.nodes.security_guardrail_node._download_image",
            return_value=(BASE64, "image/jpeg"),
        ),
        patch(
            "src.workflow.nodes.security_guardrail_node.get_llm",
            return_value=_fake_structured_llm(is_safe=True),
        ),
    ):
        debug = _run_graph(security_guardrail_node, _state()).snapshot()

    node = debug["nodes"][0]
    assert node["node"] == "security_guardrail"
    assert node["status"] == "ok"
    assert node["output"]["is_safe"] is True
    assert len(node["llm_calls"]) == 1
    assert json.loads(node["llm_calls"][0]["completion"]) == [{"is_safe": True}]
    assert debug["llm_calls_outside_nodes"] == []
    assert "route" not in debug and "judge" not in debug


def test_imagem_base64_e_query_de_url_assinada_nunca_saem():
    with (
        patch(
            "src.workflow.nodes.security_guardrail_node._download_image",
            return_value=(BASE64, "image/jpeg"),
        ),
        patch(
            "src.workflow.nodes.security_guardrail_node.get_llm",
            return_value=_fake_structured_llm(is_safe=True),
        ),
    ):
        debug = _run_graph(security_guardrail_node, _state()).snapshot()

    bruto = json.dumps(debug, ensure_ascii=False)
    assert BASE64[:40] not in bruto
    assert "data:image" not in bruto
    assert "X-Signature" not in bruto
    assert "abc123" not in bruto
    assert "[imagem omitida]" in bruto
    assert "https://bucket.exemplo.com/nr10.jpg" in bruto


def test_mask_pii_cobre_cpf_cnpj_email_e_telefone():
    texto = f"{CPF} 12.345.678/0001-95 a@b.com (11) 91234-5678"

    mascarado = mask_pii(texto)

    for original in (CPF, "12.345.678/0001-95", "a@b.com", "91234-5678"):
        assert original not in mascarado
    for marca in ("[CPF]", "[CNPJ]", "[EMAIL]", "[TELEFONE]"):
        assert marca in mascarado


def test_erro_no_no_fica_com_status_error():
    def quebra(state):
        raise RuntimeError("falhou")

    tracker = _run_graph(quebra, _state())

    node = tracker.snapshot()["nodes"][0]
    assert node["status"] == "error"
    assert node["error"] == "RuntimeError: falhou"


def test_nao_ha_teto_total_e_nenhum_no_perde_o_prompt():
    def no(state):
        return {"security_reason": "y" * 3000}

    debug = _run_graph(no, _state()).snapshot()

    assert len(json.dumps(debug, ensure_ascii=False).encode()) > 3000
    assert debug["nodes"][0]["input"] is not None


def test_prompt_longo_sem_separadores_sai_inteiro_e_rapido():
    collector = DebugTracker()
    collector._orphan_llm.append({"prompt": "y" * 2_000_000})

    inicio = time.perf_counter()
    snapshot = collector.snapshot()

    assert time.perf_counter() - inicio < 5
    assert len(snapshot["llm_calls_outside_nodes"][0]["prompt"]) == 2_000_000
    assert snapshot["truncated"] is False


async def test_prompt_grande_nao_e_descartado():
    from langchain_core.messages import SystemMessage

    tracker = DebugTracker()
    meta = {"langgraph_node": "no"}
    await tracker.on_chain_start({}, {}, run_id="n", metadata=meta, name="no")
    await tracker.on_chat_model_start(
        {}, [[SystemMessage(content="S" * 3_000_000)]], run_id="l", metadata=meta
    )
    await tracker.on_llm_end(_llm_ok("ok"), run_id="l")
    await tracker.on_chain_end({}, run_id="n")

    chamada = tracker.snapshot()["nodes"][0]["llm_calls"][0]

    assert len(chamada["prompt"][0]["content"]) == 3_000_000
    assert chamada["prompt_complete"] is True


def _llm_ok(texto):
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult

    return LLMResult(generations=[[ChatGeneration(message=AIMessage(content=texto))]])
