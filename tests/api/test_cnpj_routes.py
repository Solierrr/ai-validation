"""Testes da rota de validação de CNPJ (src/api/routes/cnpj_routes.py)."""

from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.api.routes.cnpj_routes import _sanitize_cnpj
from src.api.schemas.cnpj_schemas import CompanyLLMAuditOutput

ENDPOINT = "/api/v1/companies/validate-cnpj"
CNPJ_FORMATTED = "12.345.678/0001-90"
CNPJ_DIGITS = "12345678000190"


@contextmanager
def _mocks(company_data=None, audit=None, fetch_error=None, audit_error=None):
    """Mocka a consulta à BrasilAPI e o agente de IA usados pela rota."""
    with ExitStack() as stack:
        fetch = stack.enter_context(
            patch("src.api.routes.cnpj_routes.fetch_cnpj_data", new_callable=AsyncMock)
        )
        analyze = stack.enter_context(patch("src.api.routes.cnpj_routes.analyze_company"))

        if fetch_error is not None:
            fetch.side_effect = fetch_error
        else:
            fetch.return_value = company_data

        if audit_error is not None:
            analyze.side_effect = audit_error
        else:
            analyze.return_value = audit

        yield SimpleNamespace(fetch=fetch, analyze=analyze)


def _audit(is_compatible=True, category="ENGENHARIA_E_INSTALACOES", justification="ok"):
    return CompanyLLMAuditOutput(
        is_compatible=is_compatible,
        category_label=category,
        justification=justification,
    )


class TestSanitizeCnpj:
    """Limpeza dos caracteres não numéricos."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("12.345.678/0001-90", CNPJ_DIGITS),
            (CNPJ_DIGITS, CNPJ_DIGITS),
            ("  12 345 678 0001 90  ", CNPJ_DIGITS),
            ("12.345.678/0001-90abc", CNPJ_DIGITS),
        ],
    )
    def test_keeps_only_digits(self, raw, expected):
        assert _sanitize_cnpj(raw) == expected

    def test_returns_empty_when_there_are_no_digits(self):
        assert _sanitize_cnpj("abc-def") == ""


class TestFormatValidation:
    """Etapa 1 — validação do formato antes de qualquer chamada externa."""

    def test_rejects_cnpj_with_less_than_14_digits(self, client):
        with _mocks() as m:
            body = client.post(ENDPOINT, json={"cnpj": "123"}).json()

        assert body["status"] == "INVALID"
        assert body["error_code"] == "INVALID_CNPJ_FORMAT"
        assert body["is_active"] is False
        # Nenhuma chamada externa deve acontecer
        m.fetch.assert_not_awaited()
        m.analyze.assert_not_called()

    def test_rejects_cnpj_with_more_than_14_digits(self, client):
        with _mocks():
            body = client.post(ENDPOINT, json={"cnpj": "123456780001901234"}).json()

        assert body["error_code"] == "INVALID_CNPJ_FORMAT"

    def test_rejects_missing_field(self, client):
        assert client.post(ENDPOINT, json={}).status_code == 422


class TestNotFoundAndInactive:
    """Etapas 2 e 3 — CNPJ inexistente ou com situação cadastral irregular."""

    def test_returns_not_found_when_receita_has_no_record(self, client):
        with _mocks(company_data=None) as m:
            body = client.post(ENDPOINT, json={"cnpj": CNPJ_FORMATTED}).json()

        assert body["status"] == "INVALID"
        assert body["error_code"] == "CNPJ_NOT_FOUND"
        assert body["cnpj"] == CNPJ_DIGITS
        m.analyze.assert_not_called()

    def test_returns_inactive_with_situation_in_reason(self, client, company_data):
        company_data["descricao_situacao_cadastral"] = "BAIXADA"

        with _mocks(company_data=company_data) as m:
            body = client.post(ENDPOINT, json={"cnpj": CNPJ_FORMATTED}).json()

        assert body["error_code"] == "CNPJ_INACTIVE"
        assert body["is_active"] is False
        assert "BAIXADA" in body["reason"]
        # A razão social já é conhecida e deve ser devolvida
        assert body["company_name"] == "SOLAR ENERGY ENGENHARIA E INSTALACOES LTDA"
        m.analyze.assert_not_called()

    def test_treats_missing_situation_as_inactive(self, client, company_data):
        company_data["descricao_situacao_cadastral"] = None

        with _mocks(company_data=company_data):
            body = client.post(ENDPOINT, json={"cnpj": CNPJ_FORMATTED}).json()

        assert body["error_code"] == "CNPJ_INACTIVE"

    def test_accepts_lowercase_situation(self, client, company_data):
        """A comparação é feita em maiúsculas, então 'ativa' também vale."""
        company_data["descricao_situacao_cadastral"] = "ativa"

        with _mocks(company_data=company_data, audit=_audit()):
            body = client.post(ENDPOINT, json={"cnpj": CNPJ_FORMATTED}).json()

        assert body["status"] == "VALID"


class TestCompatibilityVerdict:
    """Etapas 4 e 5 — decisão do agente de IA sobre os CNAEs."""

    def test_returns_valid_for_compatible_company(self, client, company_data):
        audit = _audit(
            category="ENGENHARIA_E_INSTALACOES_ELETRICAS",
            justification="Empresa ativa e compativel com o setor solar.",
        )

        with _mocks(company_data=company_data, audit=audit):
            response = client.post(ENDPOINT, json={"cnpj": CNPJ_FORMATTED})

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "VALID"
        assert body["cnpj"] == CNPJ_DIGITS
        assert body["company_name"] == "SOLAR ENERGY ENGENHARIA E INSTALACOES LTDA"
        assert body["trade_name"] == "SOLAR ENERGY"
        assert body["is_active"] is True
        assert body["matched_category"] == "ENGENHARIA_E_INSTALACOES_ELETRICAS"
        assert body["error_code"] is None
        assert body["reason"] == "Empresa ativa e compativel com o setor solar."

    def test_returns_invalid_category_for_incompatible_company(self, client, company_data):
        audit = _audit(
            is_compatible=False,
            category="INCOMPATIVEL",
            justification="Ramo farmaceutico sem relacao com o setor eletrico.",
        )

        with _mocks(company_data=company_data, audit=audit):
            body = client.post(ENDPOINT, json={"cnpj": CNPJ_FORMATTED}).json()

        assert body["status"] == "INVALID"
        assert body["error_code"] == "INVALID_COMPANY_CATEGORY"
        # A empresa existe e está ativa — só o ramo é incompatível
        assert body["is_active"] is True
        assert body["matched_category"] is None
        assert "farmaceutico" in body["reason"]

    def test_returns_null_trade_name_when_absent(self, client, company_data):
        company_data["nome_fantasia"] = ""

        with _mocks(company_data=company_data, audit=_audit()):
            body = client.post(ENDPOINT, json={"cnpj": CNPJ_FORMATTED}).json()

        assert body["trade_name"] is None

    def test_forwards_company_data_to_agent(self, client, company_data):
        with _mocks(company_data=company_data, audit=_audit()) as m:
            client.post(ENDPOINT, json={"cnpj": CNPJ_FORMATTED})

        m.analyze.assert_called_once_with(company_data)


class TestExternalFailures:
    """Erros de integração viram status HTTP apropriados."""

    def test_returns_502_when_receita_lookup_fails(self, client):
        with _mocks(fetch_error=RuntimeError("429 Too Many Requests")):
            response = client.post(ENDPOINT, json={"cnpj": CNPJ_FORMATTED})

        assert response.status_code == 502
        assert "Receita Federal" in response.json()["detail"]

    def test_returns_500_when_agent_fails(self, client, company_data):
        with _mocks(company_data=company_data, audit_error=RuntimeError("keys estouradas")):
            response = client.post(ENDPOINT, json={"cnpj": CNPJ_FORMATTED})

        assert response.status_code == 500
        assert "compatibilidade" in response.json()["detail"].lower()
