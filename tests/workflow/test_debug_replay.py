from unittest.mock import patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from src.workflow.debug_replay import ReplayError, count_turns, run_single_node
from src.workflow.graph.graph import build_graph
from src.workflow.observability.debug_tracker import DebugTracker

THREAD = "debug:admin:run-1"
INITIAL = {
    "cert_nr10_url": "https://exemplo.com/nr10.jpg",
    "cert_nr35_url": "https://exemplo.com/nr35.jpg",
    "current_date": "2026-07-15",
}


class Eco(FakeMessagesListChatModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        texto = "|".join(str(m.content) for m in messages if m.type == "system")
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=texto))]
        )


llm = Eco(responses=[AIMessage(content="x")])


def _chama(prompt, state):
    return llm.invoke(
        [{"role": "system", "content": prompt}, HumanMessage(content="imagem")]
    ).content


def fake_security(state):
    _chama("PROMPT-SEGURANCA", state)
    return {"is_safe": True, "cert_nr10_b64": "AAAA", "cert_nr35_b64": "BBBB"}


def fake_nr10(state):
    texto = _chama("PROMPT-NR10", state)
    return {"nr10_result": {"valid": True, "eco": texto}}


def fake_nr35(state):
    texto = _chama("PROMPT-NR35", state)
    return {"nr35_result": {"valid": True, "eco": texto}}


def fake_consolidation(state):
    return {"status": "ACCEPT", "reason": "ok"}


def _app(nr10=fake_nr10):
    with (
        patch("src.workflow.graph.graph.security_guardrail_node", fake_security),
        patch("src.workflow.graph.graph.nr10_agent_node", nr10),
        patch("src.workflow.graph.graph.nr35_agent_node", fake_nr35),
        patch("src.workflow.graph.graph.consolidation_node", fake_consolidation),
    ):
        return build_graph(InMemorySaver())


async def _executa(app):
    await app.ainvoke(INITIAL, {"configurable": {"thread_id": THREAD}})


async def _rodar(app, node, overrides=None, collector=None, **kwargs):
    return await run_single_node(
        app,
        THREAD,
        turn=0,
        node=node,
        occurrence=0,
        overrides=overrides or {},
        callbacks=[collector or DebugTracker()],
        metadata={},
        tags=[],
        **kwargs,
    )


async def test_reexecuta_so_o_no_e_para_nele():
    app = _app()
    await _executa(app)
    collector = DebugTracker()

    _, proximos, aplicados = await _rodar(app, "nr10_agent", collector=collector)

    assert [n["node"] for n in collector.snapshot()["nodes"]] == ["nr10_agent"]
    assert proximos == ("nr35_agent",)
    assert aplicados == 0


async def test_prompt_editado_chega_ao_modelo_e_ao_debug():
    app = _app()
    await _executa(app)
    collector = DebugTracker()

    _, _, aplicados = await _rodar(
        app, "nr10_agent", overrides={0: {0: "PROMPT-EDITADO"}}, collector=collector
    )

    chamada = collector.snapshot()["nodes"][0]["llm_calls"][0]
    assert aplicados == 1
    assert chamada["prompt"][0]["content"] == "PROMPT-EDITADO"
    assert chamada["prompt"][0]["editable"] is True
    assert chamada["completion"] == "PROMPT-EDITADO"
    assert chamada["prompt_complete"] is True


async def test_primeiro_no_usa_o_estado_inicial():
    app = _app()
    await _executa(app)
    collector = DebugTracker()

    _, proximos, _ = await _rodar(app, "security_guardrail", collector=collector)

    assert [n["node"] for n in collector.snapshot()["nodes"]] == ["security_guardrail"]
    assert proximos == ("nr10_agent",)


async def test_no_depois_do_desvio_de_seguranca_tambem_funciona():
    app = _app()
    await _executa(app)
    collector = DebugTracker()

    _, proximos, _ = await _rodar(app, "consolidation", collector=collector)

    assert [n["node"] for n in collector.snapshot()["nodes"]] == ["consolidation"]
    assert proximos == ()


async def test_mensagem_humana_so_muda_quando_o_tipo_e_liberado():
    app = _app()
    await _executa(app)

    _, _, bloqueado = await _rodar(app, "nr10_agent", overrides={0: {1: "hackeado"}})
    _, _, liberado = await _rodar(
        app,
        "nr10_agent",
        overrides={0: {1: "novo"}},
        override_types=("system", "human"),
    )

    assert bloqueado == 0
    assert liberado == 1


async def test_retentativa_do_mesmo_no_reaproveita_a_edicao():
    chamadas = []

    def nr10_com_retentativa(state):
        chamadas.append(_chama("PROMPT-NR10", state))
        chamadas.append(_chama("PROMPT-NR10", state))
        return {"nr10_result": {"valid": True}}

    app = _app(nr10_com_retentativa)
    await _executa(app)
    chamadas.clear()

    await _rodar(app, "nr10_agent", overrides={0: {0: "EDITADO"}})

    assert chamadas == ["EDITADO", "EDITADO"]


async def test_conversa_original_e_copia_ficam_intactas():
    app = _app()
    await _executa(app)
    config = {"configurable": {"thread_id": THREAD}}
    antes = [
        s.config["configurable"]["checkpoint_id"]
        async for s in app.aget_state_history(config)
    ]

    await _rodar(app, "nr10_agent", overrides={0: {0: "X"}})

    depois = [
        s.config["configurable"]["checkpoint_id"]
        async for s in app.aget_state_history(config)
    ]
    assert depois == antes
    threads = {
        c.config["configurable"]["thread_id"] for c in app.checkpointer.list(None)
    }
    assert threads == {THREAD}


async def test_count_turns():
    app = _app()
    assert await count_turns(app, THREAD) == 0
    await _executa(app)
    assert await count_turns(app, THREAD) == 1


@pytest.mark.parametrize(
    ("kwargs", "status"),
    [({"node": "nao_existe"}, 404), ({"node": "nr10_agent", "occurrence": 3}, 404)],
)
async def test_pedidos_invalidos_viram_erro_claro(kwargs, status):
    app = _app()
    await _executa(app)

    with pytest.raises(ReplayError) as erro:
        await run_single_node(
            app,
            THREAD,
            turn=0,
            occurrence=kwargs.get("occurrence", 0),
            node=kwargs["node"],
            overrides={},
            callbacks=[],
            metadata={},
            tags=[],
        )

    assert erro.value.status == status


async def test_chamada_duplicada_pelo_wrapper_conta_uma_vez():
    from src.workflow.observability.prompt_override import PromptOverride

    override = PromptOverride("nr10_agent", {0: {0: "EDITADO"}})
    mensagens = [[SystemMessage(content="ORIGINAL"), HumanMessage(content="x")]]
    meta = {"langgraph_node": "nr10_agent"}

    await override.on_chat_model_start({}, mensagens, run_id="externa", metadata=meta)
    await override.on_chat_model_start({}, mensagens, run_id="interna", metadata=meta)

    assert override.calls == 1
    assert override.applied == 1
    assert mensagens[0][0].content == "EDITADO"
