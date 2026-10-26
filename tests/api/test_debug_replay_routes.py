import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import InMemorySaver

from src.api.routes import debug_routes
from src.api.schemas.cnpj_schemas import CompanyLLMAuditOutput
from src.workflow import debug_runs
from src.workflow.debug_runs import DebugRunStore
from src.workflow.graph.graph import build_graph
from tests.api.test_debug_routes import (
    ADMIN,
    CERT_BODY,
    CERTIFICATES,
    CNPJ,
    CNPJ_FORMATTED,
    HEADERS,
    OUTRO,
)
from tests.workflow.test_debug_replay import (
    fake_consolidation,
    fake_nr10,
    fake_nr35,
    fake_security,
)


@pytest.fixture
def debug_ligado(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "QA")
    monkeypatch.setenv("DEBUG_ADMIN_SUBS", f"{ADMIN},{OUTRO}")
    monkeypatch.setattr(
        "src.api.routes.debug_routes.decode_user_id", lambda token: ADMIN
    )


@pytest.fixture
def grafo_fake(monkeypatch):
    with (
        patch("src.workflow.graph.graph.security_guardrail_node", fake_security),
        patch("src.workflow.graph.graph.nr10_agent_node", fake_nr10),
        patch("src.workflow.graph.graph.nr35_agent_node", fake_nr35),
        patch("src.workflow.graph.graph.consolidation_node", fake_consolidation),
    ):
        graph = build_graph(InMemorySaver())
    monkeypatch.setattr(debug_routes, "debug_graph", graph)
    monkeypatch.setattr(debug_routes, "debug_runs", DebugRunStore(graph))
    return graph


def _validar(client):
    return client.post(CERTIFICATES, json=CERT_BODY, headers=HEADERS).json()


def _custom(run_id, node="nr10_agent", prompts=None):
    return {
        **CERT_BODY,
        "custom": {
            "run_id": run_id,
            "node": node,
            "stop_after_node": True,
            "prompts": prompts
            if prompts is not None
            else [
                {
                    "call": 0,
                    "prompt": [
                        {"type": "system", "content": "PROMPT NOVO"},
                        {"type": "human", "content": "[imagem omitida]"},
                    ],
                }
            ],
        },
    }


class TestCertificados:
    def test_execucao_devolve_run_id_e_turno(self, client, debug_ligado, grafo_fake):
        body = _validar(client)

        assert body["status"] == "ACCEPT"
        assert body["debug"]["turn"] == 0
        assert len(body["debug"]["run_id"]) == 36
        assert [n["node"] for n in body["debug"]["nodes"]] == [
            "security_guardrail",
            "nr10_agent",
            "nr35_agent",
            "consolidation",
        ]

    def test_prompt_nao_expoe_a_imagem_do_estado(
        self, client, debug_ligado, grafo_fake
    ):
        bruto = json.dumps(_validar(client))

        assert "AAAA" not in bruto

    def test_reexecucao_roda_so_o_no_com_o_prompt_novo(
        self, client, debug_ligado, grafo_fake
    ):
        run_id = _validar(client)["debug"]["run_id"]

        response = client.post(CERTIFICATES, json=_custom(run_id), headers=HEADERS)

        body = response.json()
        assert response.status_code == 200
        assert body["status"] is None
        assert [n["node"] for n in body["debug"]["nodes"]] == ["nr10_agent"]
        chamada = body["debug"]["nodes"][0]["llm_calls"][0]
        assert chamada["prompt"][0]["content"] == "PROMPT NOVO"
        assert chamada["completion"] == "PROMPT NOVO"
        assert body["debug"]["custom"] == {
            "run_id": run_id,
            "node": "nr10_agent",
            "turn": 0,
            "occurrence": 0,
            "stopped": True,
            "overrides_applied": 1,
            "next": ["nr35_agent"],
        }

    def test_so_o_prompt_system_e_trocado(self, client, debug_ligado, grafo_fake):
        run_id = _validar(client)["debug"]["run_id"]
        prompts = [
            {
                "call": 0,
                "prompt": [
                    {"type": "system", "content": "PROMPT-NR10"},
                    {"type": "human", "content": "hackeado"},
                ],
            }
        ]

        body = client.post(
            CERTIFICATES, json=_custom(run_id, prompts=prompts), headers=HEADERS
        ).json()

        assert body["debug"]["custom"]["overrides_applied"] == 0

    def test_execucao_inexistente_responde_404(self, client, debug_ligado, grafo_fake):
        response = client.post(
            CERTIFICATES,
            json=_custom("11111111-1111-4111-8111-111111111111"),
            headers=HEADERS,
        )

        assert response.status_code == 404
        assert "expirou" in response.json()["detail"]

    def test_execucao_de_outro_admin_responde_404(
        self, client, monkeypatch, debug_ligado, grafo_fake
    ):
        run_id = _validar(client)["debug"]["run_id"]
        monkeypatch.setattr(
            "src.api.routes.debug_routes.decode_user_id", lambda token: OUTRO
        )

        response = client.post(CERTIFICATES, json=_custom(run_id), headers=HEADERS)

        assert response.status_code == 404

    def test_execucao_vencida_responde_404(
        self, client, monkeypatch, debug_ligado, grafo_fake
    ):
        run_id = _validar(client)["debug"]["run_id"]
        monkeypatch.setattr(debug_runs, "MAX_AGE_SECONDS", -1)

        response = client.post(CERTIFICATES, json=_custom(run_id), headers=HEADERS)

        assert response.status_code == 404

    def test_no_inexistente_responde_404(self, client, debug_ligado, grafo_fake):
        run_id = _validar(client)["debug"]["run_id"]

        response = client.post(
            CERTIFICATES, json=_custom(run_id, node="nao_existe"), headers=HEADERS
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "mudanca",
        [
            {"run_id": "nao-e-uuid"},
            {"node": "Nó Inválido"},
            {"stop_after_node": False},
            {"occurrence": -1},
        ],
    )
    def test_corpo_personalizado_invalido_responde_422(
        self, client, debug_ligado, grafo_fake, mudanca
    ):
        body = _custom("11111111-1111-4111-8111-111111111111")
        body["custom"].update(mudanca)

        assert client.post(CERTIFICATES, json=body, headers=HEADERS).status_code == 422

    def test_reexecucao_exige_admin(
        self, client, monkeypatch, debug_ligado, grafo_fake
    ):
        monkeypatch.setattr(
            "src.api.routes.debug_routes.decode_user_id", lambda token: "x"
        )

        response = client.post(
            CERTIFICATES,
            json=_custom("11111111-1111-4111-8111-111111111111"),
            headers=HEADERS,
        )

        assert response.status_code == 403

    def test_reexecucao_deixa_log_sem_conteudo_do_prompt(
        self, client, debug_ligado, grafo_fake, caplog
    ):
        run_id = _validar(client)["debug"]["run_id"]

        with caplog.at_level("INFO", logger="src.api.routes.debug_routes"):
            client.post(CERTIFICATES, json=_custom(run_id), headers=HEADERS)

        linha = next(
            r.getMessage() for r in caplog.records if "personalizada" in r.getMessage()
        )
        assert ADMIN in linha
        assert "nr10_agent" in linha
        assert "PROMPT NOVO" not in linha

    def test_falha_no_no_devolve_500_com_o_run_id(
        self, client, debug_ligado, grafo_fake
    ):
        def quebra(state):
            raise RuntimeError("falhou")

        with (
            patch("src.workflow.graph.graph.security_guardrail_node", fake_security),
            patch("src.workflow.graph.graph.nr10_agent_node", quebra),
            patch("src.workflow.graph.graph.nr35_agent_node", fake_nr35),
            patch("src.workflow.graph.graph.consolidation_node", fake_consolidation),
        ):
            graph = build_graph(InMemorySaver())
        with (
            patch.object(debug_routes, "debug_graph", graph),
            patch.object(debug_routes, "debug_runs", DebugRunStore(graph)),
        ):
            response = client.post(CERTIFICATES, json=CERT_BODY, headers=HEADERS)

        body = response.json()
        assert response.status_code == 500
        assert len(body["debug"]["run_id"]) == 36
        assert body["debug"]["turn"] == 0


class TestRepositorioDeExecucoes:
    async def test_descarta_as_mais_antigas_acima_do_limite(self, monkeypatch):
        graph = AsyncMock()
        store = DebugRunStore(graph)
        monkeypatch.setattr(debug_runs, "MAX_RUNS", 2)

        for run in ("a", "b", "c"):
            await store.add("admin", run, 10)

        assert not await store.exists("admin", "a")
        assert await store.exists("admin", "b")
        assert await store.exists("admin", "c")
        graph.checkpointer.adelete_thread.assert_awaited_once_with("debug:admin:a")

    async def test_descarta_pelo_teto_de_bytes_mas_mantem_a_nova(self, monkeypatch):
        store = DebugRunStore(AsyncMock())
        monkeypatch.setattr(debug_runs, "MAX_BYTES", 100)

        await store.add("admin", "a", 60)
        await store.add("admin", "b", 60)
        await store.add("admin", "gigante", 500)

        assert not await store.exists("admin", "a")
        assert not await store.exists("admin", "b")
        assert await store.exists("admin", "gigante")

    async def test_vencidas_sao_apagadas_do_checkpointer(self, monkeypatch):
        graph = AsyncMock()
        store = DebugRunStore(graph)
        await store.add("admin", "a", 1)
        monkeypatch.setattr(debug_runs, "MAX_AGE_SECONDS", -1)

        assert not await store.exists("admin", "a")
        graph.checkpointer.adelete_thread.assert_awaited_once()

    def test_tamanho_conta_so_as_imagens(self):
        assert (
            debug_runs.estimate_size({"cert_nr10_b64": "ab", "cert_nr35_b64": "cde"})
            == 5
        )
        assert debug_runs.estimate_size({"cert_nr10_b64": None}) == 0
        assert debug_runs.estimate_size(None) == 0


class _Eco(FakeMessagesListChatModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        texto = "|".join(str(m.content) for m in messages)
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=texto))]
        )


def _llm_cnpj():
    chain = _Eco(responses=[AIMessage(content="x")]) | RunnableLambda(
        lambda msg: CompanyLLMAuditOutput(
            is_compatible=True,
            category_label="ENGENHARIA_E_INSTALACOES",
            justification=msg.content[:120],
        )
    )

    class _Llm:
        def with_structured_output(self, schema):
            return chain

    return _Llm()


class TestCnpj:
    def _post(self, client, company_data, custom=None):
        body = {"cnpj": CNPJ_FORMATTED, **({"custom": custom} if custom else {})}
        with (
            patch(
                "src.api.routes.cnpj_routes.fetch_cnpj_data",
                new=AsyncMock(return_value=company_data),
            ),
            patch(
                "src.agents.specialist.cnpj_agent.cnpj_agent.get_llm",
                return_value=_llm_cnpj(),
            ),
        ):
            return client.post(CNPJ, json=body, headers=HEADERS).json()

    def test_prompt_do_cnpj_sai_inteiro_e_editavel(
        self, client, debug_ligado, company_data
    ):
        body = self._post(client, company_data)

        chamada = body["debug"]["nodes"][0]["llm_calls"][0]
        assert chamada["prompt"][0]["type"] == "human"
        assert chamada["prompt"][0]["editable"] is True
        assert chamada["prompt_complete"] is True
        assert body["debug"]["turn"] == 0

    def test_reexecucao_troca_o_prompt_e_roda_o_fluxo_de_novo(
        self, client, debug_ligado, company_data
    ):
        custom = {
            "node": "cnpj_validation",
            "stop_after_node": True,
            "prompts": [
                {
                    "call": 0,
                    "prompt": [{"type": "human", "content": "PROMPT CNPJ NOVO"}],
                }
            ],
        }

        body = self._post(client, company_data, custom)

        assert body["status"] == "VALID"
        assert body["reason"].startswith("PROMPT CNPJ NOVO")
        assert body["debug"]["custom"] == {
            "node": "cnpj_validation",
            "turn": 0,
            "occurrence": 0,
            "stopped": True,
            "overrides_applied": 1,
            "next": [],
        }

    def test_no_diferente_de_cnpj_validation_responde_422(self, client, debug_ligado):
        custom = {"node": "outro", "stop_after_node": True, "prompts": []}

        response = client.post(
            CNPJ, json={"cnpj": CNPJ_FORMATTED, "custom": custom}, headers=HEADERS
        )

        assert response.status_code == 422
