"""Testes do módulo de LLM e do fallback para o Groq (src/core/llm/)."""

from unittest.mock import MagicMock, patch

import pytest
from ai_lib.llm import LeasedChatModel
from ai_lib.registry import RegistryClient, RegistryKeysUnavailable
from pydantic import BaseModel

from src.core.llm import (
    _is_key_exhausted_error,
    get_groq_llm,
    get_llm,
    invoke_llm_with_retry,
)
from src.core.llm.registry import registry_client


class DummyOutput(BaseModel):
    """Schema simples usado como output_schema nos testes."""

    ok: bool = True


class RateLimited(Exception):
    """Erro que simula estouro de cota (HTTP 429) vindo do provedor."""

    status_code = 429


MESSAGES = [{"role": "user", "content": "analise isso"}]


@pytest.fixture(autouse=True)
def _reset_registry_client():
    registry_client.cache_clear()
    yield
    registry_client.cache_clear()


def _structured_llm(result=None, error=None):
    """Cria um LLM estruturado fake que devolve `result` ou levanta `error`."""
    structured = MagicMock()
    if error is not None:
        structured.invoke.side_effect = error
    else:
        structured.invoke.return_value = result
    return structured


def _groq_llm(structured):
    groq = MagicMock()
    groq.with_structured_output.return_value = structured
    return groq


class TestRegistryClient:
    """Cliente do corretor de chaves."""

    def test_is_built_from_settings_and_cached(self):
        client = registry_client()

        assert isinstance(client, RegistryClient)
        assert client is registry_client()


class TestGetLlm:
    """Factory do cliente Gemini."""

    def test_uses_settings_and_vision_purpose(self):
        llm = get_llm()

        assert isinstance(llm, LeasedChatModel)
        assert llm.provider == "gemini"
        assert llm.model_name == "gemini-2.5-flash"
        assert llm.temperature == 0.0
        assert llm.purpose == "vision"
        assert llm.model_kwargs == {"timeout": 60}
        assert llm.registry is registry_client()


class TestGetGroqLlm:
    """Factory do cliente Groq (fallback)."""

    def test_uses_groq_model_and_registry(self):
        llm = get_groq_llm()

        assert isinstance(llm, LeasedChatModel)
        assert llm.provider == "groq"
        assert llm.model_name == "openai/gpt-oss-120b"
        assert llm.model_kwargs == {"timeout": 60}
        assert llm.registry is registry_client()


class TestIsKeyExhaustedError:
    """Detecção de chaves esgotadas."""

    @pytest.mark.parametrize(
        "error",
        [
            RateLimited("slow down"),
            Exception("429 Too Many Requests"),
            Exception("Error calling model (RESOURCE_EXHAUSTED): 429"),
            RegistryKeysUnavailable("none left"),
        ],
    )
    def test_detects_exhausted_keys(self, error):
        assert _is_key_exhausted_error(error) is True

    @pytest.mark.parametrize(
        "error",
        [
            Exception("404 NOT_FOUND"),
            Exception("connection reset"),
            Exception("invalid api key"),
        ],
    )
    def test_ignores_other_errors(self, error):
        assert _is_key_exhausted_error(error) is False


class TestInvokeLlmWithRetry:
    """Comportamento do fallback para o Groq."""

    def test_returns_result_from_gemini(self):
        primary = _structured_llm(result="resultado-ok")

        assert (
            invoke_llm_with_retry(primary, MESSAGES, output_schema=DummyOutput)
            == "resultado-ok"
        )

    @patch("src.core.llm.llm_retry.get_groq_llm")
    def test_does_not_fallback_when_error_is_not_key_exhaustion(self, mock_groq):
        primary = _structured_llm(error=ValueError("modelo inexistente"))

        with pytest.raises(ValueError, match="modelo inexistente"):
            invoke_llm_with_retry(primary, MESSAGES, output_schema=DummyOutput)

        mock_groq.assert_not_called()

    @patch("src.core.llm.llm_retry.get_groq_llm")
    def test_falls_back_to_groq_on_rate_limit(self, mock_groq):
        groq_structured = _structured_llm(result="ok-groq")
        mock_groq.return_value = _groq_llm(groq_structured)
        primary = _structured_llm(error=RateLimited("quota"))

        result = invoke_llm_with_retry(primary, MESSAGES, output_schema=DummyOutput)

        assert result == "ok-groq"
        mock_groq.return_value.with_structured_output.assert_called_once_with(
            DummyOutput
        )
        groq_structured.invoke.assert_called_once_with(MESSAGES)

    @patch("src.core.llm.llm_retry.get_groq_llm")
    def test_falls_back_to_groq_when_registry_has_no_available_key(self, mock_groq):
        mock_groq.return_value = _groq_llm(_structured_llm(result="ok-groq"))
        primary = _structured_llm(error=RegistryKeysUnavailable("none left"))

        assert (
            invoke_llm_with_retry(primary, MESSAGES, output_schema=DummyOutput)
            == "ok-groq"
        )

    @patch("src.core.llm.llm_retry.get_groq_llm")
    def test_does_not_use_groq_when_fallback_is_disabled(self, mock_groq):
        """Chamadas com imagens não usam Groq (sem Vision)."""
        primary = _structured_llm(error=RateLimited("quota"))

        with pytest.raises(RateLimited):
            invoke_llm_with_retry(
                primary, MESSAGES, output_schema=DummyOutput, allow_groq_fallback=False
            )

        mock_groq.assert_not_called()

    @patch("src.core.llm.llm_retry.get_groq_llm")
    def test_does_not_use_groq_without_output_schema(self, mock_groq):
        primary = _structured_llm(error=RateLimited("quota"))

        with pytest.raises(RateLimited):
            invoke_llm_with_retry(primary, MESSAGES)

        mock_groq.assert_not_called()

    @patch("src.core.llm.llm_retry.get_groq_llm")
    def test_groq_failure_propagates(self, mock_groq):
        mock_groq.return_value = _groq_llm(
            _structured_llm(error=RateLimited("groq quota"))
        )
        primary = _structured_llm(error=RateLimited("quota"))

        with pytest.raises(RateLimited, match="groq quota"):
            invoke_llm_with_retry(primary, MESSAGES, output_schema=DummyOutput)
