"""Testes do serviço de consulta à BrasilAPI (src/services/brasil_api.py)."""

from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.brasil_api import BRASIL_API_URL, MAX_RETRIES, fetch_cnpj_data

CNPJ = "12345678000190"

COMPANY_PAYLOAD = {
    "razao_social": "SOLAR ENERGY LTDA",
    "descricao_situacao_cadastral": "ATIVA",
}


def _response(status_code, json_data=None, raise_error=None):
    """Resposta HTTP fake da BrasilAPI."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data or {}
    if raise_error is not None:
        response.raise_for_status.side_effect = raise_error
    else:
        response.raise_for_status.return_value = None
    return response


@contextmanager
def _mocks(responses):
    """
    Mocka o httpx.AsyncClient e o asyncio.sleep do módulo.

    `responses` é a lista de respostas devolvidas em sequência pelo .get().
    O sleep é mockado para os testes de retry não esperarem de verdade.
    """
    with ExitStack() as stack:
        mock_client_cls = stack.enter_context(patch("src.services.brasil_api.httpx.AsyncClient"))
        mock_sleep = stack.enter_context(
            patch("src.services.brasil_api.asyncio.sleep", new_callable=AsyncMock)
        )

        client = AsyncMock()
        if len(responses) == 1:
            client.get.return_value = responses[0]
        else:
            client.get.side_effect = responses
        mock_client_cls.return_value.__aenter__.return_value = client

        yield SimpleNamespace(client_cls=mock_client_cls, client=client, sleep=mock_sleep)


class TestSuccessfulLookup:
    """Consulta bem-sucedida (HTTP 200)."""

    async def test_returns_company_data(self):
        with _mocks([_response(200, COMPANY_PAYLOAD)]):
            result = await fetch_cnpj_data(CNPJ)

        assert result == COMPANY_PAYLOAD

    async def test_calls_expected_url(self):
        with _mocks([_response(200, COMPANY_PAYLOAD)]) as m:
            await fetch_cnpj_data(CNPJ)

        m.client.get.assert_awaited_once_with(BRASIL_API_URL.format(cnpj=CNPJ))

    async def test_uses_timeout(self):
        with _mocks([_response(200, COMPANY_PAYLOAD)]) as m:
            await fetch_cnpj_data(CNPJ)

        assert m.client_cls.call_args.kwargs["timeout"] == 15.0


class TestNotFoundHandling:
    """CNPJ inexistente ou inválido — a BrasilAPI responde 404 ou 400."""

    @pytest.mark.parametrize("status_code", [400, 404])
    async def test_returns_none(self, status_code):
        with _mocks([_response(status_code)]):
            result = await fetch_cnpj_data(CNPJ)

        assert result is None

    async def test_does_not_retry(self):
        """404 é definitivo, não deve haver espera nem nova tentativa."""
        with _mocks([_response(404)]) as m:
            await fetch_cnpj_data(CNPJ)

        m.client.get.assert_awaited_once()
        m.sleep.assert_not_awaited()


class TestRateLimitRetry:
    """Retry com backoff exponencial quando a BrasilAPI responde 429."""

    def test_max_retries_constant(self):
        assert MAX_RETRIES == 3

    async def test_retries_and_succeeds_on_second_attempt(self):
        responses = [_response(429), _response(200, COMPANY_PAYLOAD)]

        with _mocks(responses) as m:
            result = await fetch_cnpj_data(CNPJ)

        assert result == COMPANY_PAYLOAD
        assert m.client.get.await_count == 2
        m.sleep.assert_awaited_once_with(2)

    async def test_uses_exponential_backoff(self):
        """Esperas de 2s, 4s e 8s entre as tentativas."""
        responses = [_response(429), _response(429), _response(429)]

        with _mocks(responses) as m:
            await fetch_cnpj_data(CNPJ)

        waits = [call.args[0] for call in m.sleep.await_args_list]
        assert waits == [2, 4, 8]

    async def test_returns_none_when_retries_are_exhausted(self):
        responses = [_response(429), _response(429), _response(429)]

        with _mocks(responses):
            result = await fetch_cnpj_data(CNPJ)

        assert result is None

    async def test_propagates_error_when_retries_exhausted_and_status_raises(self):
        error = RuntimeError("429 Too Many Requests")
        responses = [_response(429, raise_error=error) for _ in range(MAX_RETRIES)]

        with _mocks(responses):
            with pytest.raises(RuntimeError, match="429"):
                await fetch_cnpj_data(CNPJ)


class TestServerErrors:
    """Erros não tratados devem propagar para a rota decidir o HTTP status."""

    async def test_raises_on_server_error(self):
        error = RuntimeError("500 Internal Server Error")

        with _mocks([_response(500, raise_error=error)]):
            with pytest.raises(RuntimeError, match="500"):
                await fetch_cnpj_data(CNPJ)

    async def test_raises_on_connection_failure(self):
        with _mocks([_response(200)]) as m:
            m.client.get.side_effect = RuntimeError("connection refused")

            with pytest.raises(RuntimeError, match="connection refused"):
                await fetch_cnpj_data(CNPJ)
