"""Testes das rotas de debug (src/api/routes/debug_routes.py)."""

import json
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest

from src.api.schemas.cnpj_schemas import CompanyLLMAuditOutput

CERTIFICATES = "/debug/certificates/validate"
CNPJ = "/debug/companies/validate-cnpj"
ADMIN = "11111111-1111-4111-8111-111111111111"
OUTRO = "22222222-2222-4222-8222-222222222222"
HEADERS = {"Authorization": "Bearer jwt-de-teste"}
CERT_BODY = {
    "cert_nr10_url": "https://exemplo.com/nr10.jpg?X-Signature=abc123",
    "cert_nr35_url": "https://exemplo.com/nr35.png",
}
CNPJ_FORMATTED = "12.345.678/0001-90"
CNPJ_DIGITS = "12345678000190"
ACCEPT_RESULT = {
    "status": "ACCEPT",
    "reason": "Certificados válidos.",
    "error_code": None,
    "extracted_data": None,
}


@pytest.fixture
def debug_ligado(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "QA")
    monkeypatch.setenv("DEBUG_ADMIN_SUBS", ADMIN)
    monkeypatch.setattr("src.api.routes.debug_routes.decode_user_id", lambda token: ADMIN)


def _graph(result=None, error=None):
    graph = AsyncMock()
    if error is not None:
        graph.ainvoke.side_effect = error
    else:
        graph.ainvoke.return_value = result or ACCEPT_RESULT
    return patch("src.api.routes.debug_routes.compiled_graph", graph)


class TestAccess:
    def test_sem_admins_configurados_responde_404(self, client, monkeypatch):
        monkeypatch.setenv("DEBUG_ADMIN_SUBS", "")

        assert client.post(CERTIFICATES, json=CERT_BODY, headers=HEADERS).status_code == 404

    @pytest.mark.parametrize("ambiente", ["PRD", "staging", ""])
    def test_ambiente_fora_da_lista_responde_404(self, client, monkeypatch, debug_ligado, ambiente):
        monkeypatch.setenv("ENVIRONMENT", ambiente)

        assert client.post(CERTIFICATES, json=CERT_BODY, headers=HEADERS).status_code == 404

    @pytest.mark.parametrize("ambiente", ["dev", " qa ", "prod"])
    def test_ambientes_permitidos_ignoram_caixa_e_espacos(
        self, client, monkeypatch, debug_ligado, ambiente
    ):
        monkeypatch.setenv("ENVIRONMENT", ambiente)

        with _graph():
            response = client.post(CERTIFICATES, json=CERT_BODY, headers=HEADERS)

        assert response.status_code == 200

    def test_sem_token_responde_401(self, client, debug_ligado):
        assert client.post(CERTIFICATES, json=CERT_BODY).status_code == 401

    def test_token_invalido_responde_401(self, client, monkeypatch, debug_ligado):
        monkeypatch.setattr("src.api.routes.debug_routes.decode_user_id", lambda token: None)

        assert client.post(CERTIFICATES, json=CERT_BODY, headers=HEADERS).status_code == 401

    def test_usuario_fora_da_lista_responde_403(self, client, monkeypatch, debug_ligado):
        monkeypatch.setattr("src.api.routes.debug_routes.decode_user_id", lambda token: OUTRO)

        assert client.post(CERTIFICATES, json=CERT_BODY, headers=HEADERS).status_code == 403

    def test_lista_com_lixo_e_maiusculas_funciona(self, client, monkeypatch, debug_ligado):
        monkeypatch.setenv("DEBUG_ADMIN_SUBS", f" lixo , {OUTRO} ,, {ADMIN.upper()} ")

        with _graph():
            response = client.post(CERTIFICATES, json=CERT_BODY, headers=HEADERS)

        assert response.status_code == 200

    def test_rotas_ficam_fora_do_openapi(self, client, debug_ligado):
        paths = client.get("/openapi.json").json()["paths"]

        assert not any(path.startswith("/debug") for path in paths)


class TestCertificates:
    def test_aprovado_devolve_o_debug_sem_persistir(self, client, debug_ligado):
        with _graph():
            response = client.post(CERTIFICATES, json=CERT_BODY, headers=HEADERS)

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "ACCEPT"
        assert body["debug"]["persisted"] is False
        assert body["debug"]["environment"] == "QA"

    def test_falha_devolve_500_com_debug_parcial_e_pii_mascarado(self, client, debug_ligado):
        with _graph(error=RuntimeError("falha com 123.456.789-09")):
            response = client.post(CERTIFICATES, json=CERT_BODY, headers=HEADERS)

        body = response.json()
        assert response.status_code == 500
        assert "RuntimeError" in body["detail"]
        assert "123.456.789-09" not in body["detail"]
        assert body["debug"]["nodes"] == []

    def test_corpo_invalido_responde_422(self, client, debug_ligado):
        assert client.post(CERTIFICATES, json={}, headers=HEADERS).status_code == 422


def _cnpj_mocks(company_data=None, audit=None, fetch_error=None):
    stack = ExitStack()
    fetch = stack.enter_context(
        patch("src.api.routes.cnpj_routes.fetch_cnpj_data", new_callable=AsyncMock)
    )
    analyze = stack.enter_context(patch("src.api.routes.cnpj_routes.analyze_company"))
    if fetch_error is not None:
        fetch.side_effect = fetch_error
    else:
        fetch.return_value = company_data
    analyze.return_value = audit
    return stack


class TestCnpj:
    def test_fluxo_real_vira_uma_etapa_e_nao_expoe_o_cnpj(self, client, debug_ligado, company_data):
        audit = CompanyLLMAuditOutput(
            is_compatible=True, category_label="ENGENHARIA_E_INSTALACOES", justification="ok"
        )

        with _cnpj_mocks(company_data=company_data, audit=audit):
            response = client.post(CNPJ, json={"cnpj": CNPJ_FORMATTED}, headers=HEADERS)

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "VALID"
        assert [node["node"] for node in body["debug"]["nodes"]] == ["cnpj_validation"]
        assert body["debug"]["nodes"][0]["status"] == "ok"
        bruto = json.dumps(body["debug"], ensure_ascii=False)
        assert CNPJ_FORMATTED not in bruto
        assert CNPJ_DIGITS not in bruto

    def test_erro_da_brasilapi_devolve_502_com_debug(self, client, debug_ligado):
        with _cnpj_mocks(fetch_error=RuntimeError("fora do ar")):
            response = client.post(CNPJ, json={"cnpj": CNPJ_FORMATTED}, headers=HEADERS)

        body = response.json()
        assert response.status_code == 502
        assert "fora do ar" in body["detail"]
        assert body["debug"]["nodes"][0]["status"] == "error"

    def test_formato_invalido_devolve_o_codigo_de_erro(self, client, debug_ligado):
        with _cnpj_mocks():
            response = client.post(CNPJ, json={"cnpj": "123"}, headers=HEADERS)

        body = response.json()
        assert response.status_code == 200
        assert body["error_code"] == "INVALID_CNPJ_FORMAT"
        assert body["debug"]["persisted"] is False
