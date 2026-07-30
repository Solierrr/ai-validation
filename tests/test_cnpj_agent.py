"""Testes do agente auditor de CNPJ (src/agents/cnpj_agent.py)."""

from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.agents.cnpj_agent import _format_cnaes_secundarios, analyze_company
from src.api.cnpj_schemas import CompanyLLMAuditOutput


@contextmanager
def _mocks():
    """Patches do LLM usados pelo agente de CNPJ."""
    with ExitStack() as stack:
        yield SimpleNamespace(
            get_llm=stack.enter_context(patch("src.agents.cnpj_agent.get_llm")),
            invoke=stack.enter_context(
                patch("src.agents.cnpj_agent.invoke_llm_with_retry")
            ),
        )


def _compatible_output():
    return CompanyLLMAuditOutput(
        is_compatible=True,
        category_label="ENGENHARIA_E_INSTALACOES",
        justification="Empresa atua em instalacoes eletricas.",
    )


class TestFormatCnaesSecundarios:
    """Formatação da lista de CNAEs secundários para o prompt."""

    def test_returns_placeholder_when_list_is_empty(self):
        assert "Nenhum CNAE secundário registrado" in _format_cnaes_secundarios([])

    def test_returns_placeholder_when_list_is_none(self):
        assert "Nenhum CNAE secundário registrado" in _format_cnaes_secundarios(None)

    def test_formats_each_cnae_as_bullet(self):
        result = _format_cnaes_secundarios(
            [
                {"codigo": 4321500, "descricao": "Instalacao eletrica"},
                {"codigo": 7112000, "descricao": "Servicos de engenharia"},
            ]
        )

        assert "- 4321500 - Instalacao eletrica" in result
        assert "- 7112000 - Servicos de engenharia" in result

    def test_uses_fallbacks_for_missing_fields(self):
        result = _format_cnaes_secundarios([{}])

        assert "N/A" in result
        assert "Descrição não disponível" in result


class TestAnalyzeCompanyPrompt:
    """Montagem do prompt enviado ao LLM."""

    def _prompt_from(self, mock_invoke):
        """Extrai o texto do prompt da chamada ao LLM."""
        return mock_invoke.call_args.args[1][0]["content"]

    def test_includes_company_identification(self, company_data):
        with _mocks() as m:
            m.invoke.return_value = _compatible_output()

            analyze_company(company_data)

            prompt = self._prompt_from(m.invoke)
            assert "SOLAR ENERGY ENGENHARIA E INSTALACOES LTDA" in prompt
            assert "SOLAR ENERGY" in prompt

    def test_includes_primary_and_secondary_cnaes(self, company_data):
        with _mocks() as m:
            m.invoke.return_value = _compatible_output()

            analyze_company(company_data)

            prompt = self._prompt_from(m.invoke)
            assert "Instalacao e manutencao eletrica" in prompt
            assert "Servicos de engenharia" in prompt

    def test_uses_fallback_when_trade_name_is_none(self, company_data):
        company_data["nome_fantasia"] = None
        with _mocks() as m:
            m.invoke.return_value = _compatible_output()

            analyze_company(company_data)

            assert "Não informado" in self._prompt_from(m.invoke)

    def test_uses_fallback_when_company_name_is_absent(self, company_data):
        company_data.pop("razao_social")
        with _mocks() as m:
            m.invoke.return_value = _compatible_output()

            analyze_company(company_data)

            assert "Não informada" in self._prompt_from(m.invoke)


class TestAnalyzeCompanyResult:
    """Retorno do agente e configuração da chamada ao LLM."""

    def test_returns_compatible_verdict(self, company_data):
        with _mocks() as m:
            m.invoke.return_value = _compatible_output()

            result = analyze_company(company_data)

            assert result.is_compatible is True
            assert result.category_label == "ENGENHARIA_E_INSTALACOES"
            assert "instalacoes" in result.justification

    def test_returns_incompatible_verdict(self, company_data):
        with _mocks() as m:
            m.invoke.return_value = CompanyLLMAuditOutput(
                is_compatible=False,
                category_label="INCOMPATIVEL",
                justification="Ramo farmaceutico sem relacao com o setor eletrico.",
            )

            result = analyze_company(company_data)

            assert result.is_compatible is False
            assert result.category_label == "INCOMPATIVEL"

    def test_requests_structured_output(self, company_data):
        with _mocks() as m:
            m.invoke.return_value = _compatible_output()

            analyze_company(company_data)

            assert m.invoke.call_args.kwargs["output_schema"] is CompanyLLMAuditOutput

    def test_allows_groq_fallback_because_prompt_is_text_only(self, company_data):
        """Sem imagem no prompt, o Groq pode assumir se o Gemini estourar."""
        with _mocks() as m:
            m.invoke.return_value = _compatible_output()

            analyze_company(company_data)

            assert "allow_groq_fallback" not in m.invoke.call_args.kwargs

    def test_propagates_llm_failure(self, company_data):
        """O agente não engole erros — a rota decide o status HTTP."""
        with _mocks() as m:
            m.invoke.side_effect = RuntimeError("todas as keys estouraram")

            with pytest.raises(RuntimeError, match="estouraram"):
                analyze_company(company_data)
