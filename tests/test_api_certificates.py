"""Testes da rota de validação de certificados (src/api/routes.py)."""

from datetime import date
from unittest.mock import AsyncMock, patch

ENDPOINT = "/api/v1/certificates/validate"

VALID_PAYLOAD = {
    "cert_nr10_url": "https://exemplo.com/nr10.jpg",
    "cert_nr35_url": "https://exemplo.com/nr35.png",
}

ACCEPT_RESULT = {
    "status": "ACCEPT",
    "reason": "Certificados válidos e do mesmo profissional.",
    "error_code": None,
    "extracted_data": {"detected_student_name": "Carlos Eduardo da Silva"},
}


class TestRequestValidation:
    """Validação do payload de entrada pelo Pydantic."""

    def test_rejects_empty_body(self, client):
        assert client.post(ENDPOINT, json={}).status_code == 422

    def test_rejects_malformed_urls(self, client):
        response = client.post(
            ENDPOINT,
            json={"cert_nr10_url": "nao-e-url", "cert_nr35_url": "tambem-nao"},
        )

        assert response.status_code == 422

    def test_rejects_missing_nr35_url(self, client):
        response = client.post(ENDPOINT, json={"cert_nr10_url": "https://exemplo.com/a.jpg"})

        assert response.status_code == 422


class TestPipelineResults:
    """Tradução do resultado da pipeline para a resposta HTTP."""

    @patch("src.api.routes.compiled_graph")
    def test_returns_accept(self, mock_graph, client):
        mock_graph.ainvoke = AsyncMock(return_value=ACCEPT_RESULT)

        response = client.post(ENDPOINT, json=VALID_PAYLOAD)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ACCEPT"
        assert body["error_code"] is None
        assert body["extracted_data"]["detected_student_name"] == "Carlos Eduardo da Silva"

    @patch("src.api.routes.compiled_graph")
    def test_returns_rejected_with_error_code(self, mock_graph, client):
        mock_graph.ainvoke = AsyncMock(
            return_value={
                "status": "REJECTED",
                "reason": "A NR-35 possui apenas 4h.",
                "error_code": "INSUFFICIENT_WORKLOAD",
                "extracted_data": None,
            }
        )

        response = client.post(ENDPOINT, json=VALID_PAYLOAD)

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "REJECTED"
        assert body["error_code"] == "INSUFFICIENT_WORKLOAD"
        assert body["extracted_data"] is None

    @patch("src.api.routes.compiled_graph")
    def test_defaults_to_rejected_when_pipeline_returns_nothing(self, mock_graph, client):
        """Sem status no resultado, a resposta assume REJECTED (fail-safe)."""
        mock_graph.ainvoke = AsyncMock(return_value={})

        body = client.post(ENDPOINT, json=VALID_PAYLOAD).json()

        assert body["status"] == "REJECTED"
        assert "desconhecido" in body["reason"].lower()


class TestInitialState:
    """Estado inicial montado pela rota antes de invocar a pipeline."""

    @patch("src.api.routes.compiled_graph")
    def test_forwards_urls_as_strings(self, mock_graph, client):
        mock_graph.ainvoke = AsyncMock(return_value=ACCEPT_RESULT)

        client.post(ENDPOINT, json=VALID_PAYLOAD)

        state = mock_graph.ainvoke.await_args.args[0]
        assert state["cert_nr10_url"] == VALID_PAYLOAD["cert_nr10_url"]
        assert state["cert_nr35_url"] == VALID_PAYLOAD["cert_nr35_url"]
        assert isinstance(state["cert_nr10_url"], str)

    @patch("src.api.routes.compiled_graph")
    def test_injects_current_date(self, mock_graph, client):
        """A data de referência é injetada pelo servidor, não pelo cliente."""
        mock_graph.ainvoke = AsyncMock(return_value=ACCEPT_RESULT)

        client.post(ENDPOINT, json=VALID_PAYLOAD)

        state = mock_graph.ainvoke.await_args.args[0]
        assert state["current_date"] == date.today().isoformat()


class TestErrorHandling:
    """Falhas inesperadas da pipeline."""

    @patch("src.api.routes.compiled_graph")
    def test_returns_500_on_pipeline_failure(self, mock_graph, client):
        mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        response = client.post(ENDPOINT, json=VALID_PAYLOAD)

        assert response.status_code == 500
        assert "pipeline" in response.json()["detail"].lower()


class TestRateLimiting:
    """Proteção contra abuso: 10 requisições por minuto por IP."""

    @patch("src.api.routes.compiled_graph")
    def test_returns_429_after_exceeding_limit(self, mock_graph, client):
        from src.api import routes

        mock_graph.ainvoke = AsyncMock(return_value=ACCEPT_RESULT)

        # O limiter é desligado por padrão nos testes (ver conftest)
        routes.limiter.enabled = True
        routes.limiter.reset()

        statuses = [
            client.post(ENDPOINT, json=VALID_PAYLOAD).status_code for _ in range(11)
        ]

        assert statuses[:10] == [200] * 10
        assert statuses[10] == 429
