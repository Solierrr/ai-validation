"""
Testes dos agentes especialistas NR-10 e NR-35.

Os dois agentes têm o mesmo fluxo (cache de imagem → LLM Vision → output
estruturado), mudando apenas as regras do prompt. Por isso os testes são
parametrizados para rodar contra os dois módulos sem duplicar código.
"""

import base64
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.agents.nr10_agent import NRAgentOutput, nr10_agent_node
from src.agents.nr35_agent import NR35AgentOutput, nr35_agent_node

IMAGE_BYTES = b"fake-certificate-bytes"
EXPECTED_B64 = base64.b64encode(IMAGE_BYTES).decode("utf-8")
CURRENT_DATE = "2026-07-15"

# (módulo, função do nó, prefixo das chaves no state, schema de saída)
AGENTS = [
    pytest.param(
        SimpleNamespace(
            module="src.agents.nr10_agent",
            node=nr10_agent_node,
            prefix="nr10",
            schema=NRAgentOutput,
        ),
        id="nr10",
    ),
    pytest.param(
        SimpleNamespace(
            module="src.agents.nr35_agent",
            node=nr35_agent_node,
            prefix="nr35",
            schema=NR35AgentOutput,
        ),
        id="nr35",
    ),
]


@contextmanager
def _mocks(module):
    """Aplica os patches de httpx, get_llm e invoke_llm_with_retry do módulo."""
    with ExitStack() as stack:
        yield SimpleNamespace(
            client=stack.enter_context(patch(f"{module}.httpx.Client")),
            get_llm=stack.enter_context(patch(f"{module}.get_llm")),
            invoke=stack.enter_context(patch(f"{module}.invoke_llm_with_retry")),
        )


def _wire_download(mock_client_cls, error=None):
    """Configura o httpx.Client mockado com bytes de imagem ou erro."""
    client = mock_client_cls.return_value.__enter__.return_value
    if error is not None:
        client.get.side_effect = error
        return client

    response = MagicMock()
    response.content = IMAGE_BYTES
    response.headers = {"content-type": "image/jpeg"}
    response.raise_for_status.return_value = None
    client.get.return_value = response
    return client


def _valid_output(schema):
    """Instância de saída válida do agente."""
    return schema(
        valid=True,
        error_code=None,
        error_reason=None,
        student_name="Carlos Eduardo da Silva",
        institution_name="SENAI SP",
        workload_hours=40,
        issue_date="2026-01-15",
        has_required_structure=True,
    )


def _state_with_cache(agent):
    """State já com a imagem em cache (cenário normal da pipeline)."""
    return {
        f"cert_{agent.prefix}_url": "https://exemplo.com/cert.jpg",
        f"cert_{agent.prefix}_b64": EXPECTED_B64,
        f"cert_{agent.prefix}_mime": "image/png",
        "current_date": CURRENT_DATE,
    }


def _state_without_cache(agent):
    """State sem cache — o agente precisa baixar a imagem."""
    return {
        f"cert_{agent.prefix}_url": "https://exemplo.com/cert.jpg",
        "current_date": CURRENT_DATE,
    }


@pytest.mark.parametrize("agent", AGENTS)
class TestImageSource:
    """Origem da imagem: cache do guardrail ou download próprio."""

    def test_reuses_cached_image_without_downloading(self, agent):
        with _mocks(agent.module) as m:
            m.invoke.return_value = _valid_output(agent.schema)

            agent.node(_state_with_cache(agent))

            # O guardrail já baixou a imagem, então não deve haver novo request
            m.client.assert_not_called()

    def test_downloads_when_cache_is_empty(self, agent):
        with _mocks(agent.module) as m:
            client = _wire_download(m.client)
            m.invoke.return_value = _valid_output(agent.schema)

            agent.node(_state_without_cache(agent))

            client.get.assert_called_once_with("https://exemplo.com/cert.jpg")

    def test_sends_cached_mime_type_in_data_url(self, agent):
        with _mocks(agent.module) as m:
            m.invoke.return_value = _valid_output(agent.schema)

            agent.node(_state_with_cache(agent))

            messages = m.invoke.call_args.args[1]
            image_part = messages[1].content[1]
            assert image_part["image_url"]["url"] == f"data:image/png;base64,{EXPECTED_B64}"


@pytest.mark.parametrize("agent", AGENTS)
class TestSuccessfulExtraction:
    """Extração bem-sucedida dos dados do certificado."""

    def test_returns_agent_output_as_dict(self, agent):
        with _mocks(agent.module) as m:
            m.invoke.return_value = _valid_output(agent.schema)

            result = agent.node(_state_with_cache(agent))

            data = result[f"{agent.prefix}_result"]
            assert data["valid"] is True
            assert data["student_name"] == "Carlos Eduardo da Silva"
            assert data["workload_hours"] == 40
            assert data["issue_date"] == "2026-01-15"
            assert data["has_required_structure"] is True

    def test_injects_current_date_into_system_prompt(self, agent):
        with _mocks(agent.module) as m:
            m.invoke.return_value = _valid_output(agent.schema)

            agent.node(_state_with_cache(agent))

            system_prompt = m.invoke.call_args.args[1][0]["content"]
            assert CURRENT_DATE in system_prompt

    def test_disables_groq_fallback_because_of_vision(self, agent):
        """Groq não processa imagens, então o fallback fica desligado."""
        with _mocks(agent.module) as m:
            m.invoke.return_value = _valid_output(agent.schema)

            agent.node(_state_with_cache(agent))

            assert m.invoke.call_args.kwargs["allow_groq_fallback"] is False

    def test_requests_structured_output_with_agent_schema(self, agent):
        with _mocks(agent.module) as m:
            m.invoke.return_value = _valid_output(agent.schema)

            agent.node(_state_with_cache(agent))

            assert m.invoke.call_args.kwargs["output_schema"] is agent.schema


@pytest.mark.parametrize("agent", AGENTS)
class TestFailureHandling:
    """Tratamento de falhas — sempre resulta em certificado inválido."""

    def test_returns_illegible_document_when_download_fails(self, agent):
        with _mocks(agent.module) as m:
            _wire_download(m.client, error=RuntimeError("timeout"))

            result = agent.node(_state_without_cache(agent))

            data = result[f"{agent.prefix}_result"]
            assert data["valid"] is False
            assert data["error_code"] == "ILLEGIBLE_DOCUMENT"
            assert "timeout" in data["error_reason"]
            assert data["has_required_structure"] is False
            # Sem imagem não faz sentido chamar o LLM
            m.invoke.assert_not_called()

    def test_returns_illegible_document_when_llm_fails(self, agent):
        with _mocks(agent.module) as m:
            m.invoke.side_effect = RuntimeError("rate limit em todas as keys")

            result = agent.node(_state_with_cache(agent))

            data = result[f"{agent.prefix}_result"]
            assert data["valid"] is False
            assert data["error_code"] == "ILLEGIBLE_DOCUMENT"
            assert data["student_name"] is None
            assert data["workload_hours"] is None
