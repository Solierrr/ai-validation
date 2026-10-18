"""Testes do módulo de LLM e da cadeia de fallback (src/core/llm/)."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from src.core.llm import (
    _is_rate_limit_error,
    get_groq_llm,
    get_llm,
    get_openai_llm,
    invoke_llm_with_retry,
)


class DummyOutput(BaseModel):
    """Schema simples usado como output_schema nos testes."""

    ok: bool = True


# Erro que simula estouro de cota (o que o Gemini/Groq retornam com HTTP 429)
RATE_LIMIT_ERROR = Exception("429 RESOURCE_EXHAUSTED: quota exceeded")

MESSAGES = [{"role": "user", "content": "analise isso"}]


def _mock_llm(result=None, error=None):
    """Cria um LLM fake; com `error`, .invoke() e o structured output levantam esse erro."""
    llm = MagicMock()
    structured = MagicMock()

    if error is not None:
        llm.invoke.side_effect = error
        structured.invoke.side_effect = error
    else:
        llm.invoke.return_value = result
        structured.invoke.return_value = result

    llm.with_structured_output.return_value = structured
    return llm


class TestFactories:
    """Fábricas dos clientes: um por provedor, com a chave lida do ambiente."""

    def test_gemini_uses_settings_model_and_temperature(self):
        llm = get_llm()

        assert llm.provider == "gemini"
        assert llm.model_name == "gemini-2.5-flash"
        assert llm.temperature == 0.0
        assert llm.model_kwargs["timeout"] == 60

    def test_gemini_model_can_come_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL_GEMINI", "gemini-outro")

        assert get_llm().model_name == "gemini-outro"

    def test_groq_uses_the_current_default_model(self):
        llm = get_groq_llm()

        assert llm.provider == "groq"
        assert llm.model_name == "openai/gpt-oss-120b"

    def test_openai_model_comes_from_the_environment(self):
        llm = get_openai_llm()

        assert llm.provider == "openai"
        assert llm.model_name == "gpt-6-luna"

    def test_openai_without_model_fails_clearly(self, monkeypatch):
        monkeypatch.delenv("LLM_MODEL_OPENAI")

        with pytest.raises(ValueError, match="LLM_MODEL_OPENAI"):
            get_openai_llm()


class TestIsRateLimitError:
    """Detecção de erro de cota estourada."""

    @pytest.mark.parametrize(
        "message",
        [
            "429 Too Many Requests",
            "RESOURCE_EXHAUSTED",
            "Error calling model (RESOURCE_EXHAUSTED): 429",
        ],
    )
    def test_detects_rate_limit(self, message):
        assert _is_rate_limit_error(Exception(message)) is True

    @pytest.mark.parametrize(
        "message",
        ["404 NOT_FOUND", "invalid api key", "connection reset"],
    )
    def test_ignores_other_errors(self, message):
        assert _is_rate_limit_error(Exception(message)) is False


class TestInvokeSuccessAndErrors:
    """Comportamento da primeira tentativa (Gemini)."""

    def test_returns_result_from_primary(self):
        primary = _mock_llm(result="resultado-ok").with_structured_output(DummyOutput)

        assert invoke_llm_with_retry(primary, MESSAGES) == "resultado-ok"

    @patch("src.core.llm.llm_retry.get_groq_llm")
    def test_does_not_fallback_when_error_is_not_rate_limit(self, mock_groq):
        primary = _mock_llm(
            error=ValueError("modelo inexistente")
        ).with_structured_output(DummyOutput)

        with pytest.raises(ValueError, match="modelo inexistente"):
            invoke_llm_with_retry(primary, MESSAGES, output_schema=DummyOutput)

        mock_groq.assert_not_called()


@patch("src.core.llm.llm_retry.get_openai_llm")
@patch("src.core.llm.llm_retry.get_groq_llm")
class TestProviderFallback:
    """Fallback entre provedores quando o Gemini estoura a cota."""

    def test_falls_back_to_groq_first_then_openai(self, mock_groq, mock_openai):
        mock_groq.return_value = _mock_llm(result="ok-groq")
        primary = _mock_llm(error=RATE_LIMIT_ERROR).with_structured_output(DummyOutput)

        result = invoke_llm_with_retry(primary, MESSAGES, output_schema=DummyOutput)

        assert result == "ok-groq"
        mock_openai.assert_not_called()

    def test_falls_back_to_openai_when_groq_is_also_exhausted(
        self, mock_groq, mock_openai
    ):
        mock_groq.return_value = _mock_llm(error=RATE_LIMIT_ERROR)
        mock_openai.return_value = _mock_llm(result="ok-openai")
        primary = _mock_llm(error=RATE_LIMIT_ERROR).with_structured_output(DummyOutput)

        result = invoke_llm_with_retry(primary, MESSAGES, output_schema=DummyOutput)

        assert result == "ok-openai"

    def test_skips_text_only_providers_for_vision_calls(self, mock_groq, mock_openai):
        """Chamadas com imagem passam allow_groq_fallback=False (Groq não tem Vision)."""
        mock_openai.return_value = _mock_llm(result="ok-openai-vision")
        primary = _mock_llm(error=RATE_LIMIT_ERROR).with_structured_output(DummyOutput)

        result = invoke_llm_with_retry(
            primary, MESSAGES, output_schema=DummyOutput, allow_groq_fallback=False
        )

        assert result == "ok-openai-vision"
        mock_groq.assert_not_called()

    def test_follows_the_configured_provider_order(
        self, mock_groq, mock_openai, monkeypatch
    ):
        monkeypatch.setenv("LLM_PROVIDER_ORDER", "gemini,openai,groq")
        mock_openai.return_value = _mock_llm(result="ok-openai")
        primary = _mock_llm(error=RATE_LIMIT_ERROR).with_structured_output(DummyOutput)

        assert (
            invoke_llm_with_retry(primary, MESSAGES, output_schema=DummyOutput)
            == "ok-openai"
        )
        mock_groq.assert_not_called()

    def test_invokes_llm_directly_when_no_output_schema(self, mock_groq, mock_openai):
        fallback = _mock_llm(result="ok-cru")
        mock_groq.return_value = fallback
        primary = _mock_llm(error=RATE_LIMIT_ERROR)

        assert invoke_llm_with_retry(primary, MESSAGES) == "ok-cru"
        fallback.with_structured_output.assert_not_called()

    def test_raises_when_every_provider_is_exhausted(self, mock_groq, mock_openai):
        mock_groq.return_value = _mock_llm(error=RATE_LIMIT_ERROR)
        mock_openai.return_value = _mock_llm(error=RATE_LIMIT_ERROR)
        primary = _mock_llm(error=RATE_LIMIT_ERROR).with_structured_output(DummyOutput)

        with pytest.raises(Exception, match="rate limit"):
            invoke_llm_with_retry(primary, MESSAGES, output_schema=DummyOutput)

    def test_propagates_non_rate_limit_error_from_fallback(
        self, mock_groq, mock_openai
    ):
        mock_groq.return_value = _mock_llm(error=ValueError("chave inválida"))
        primary = _mock_llm(error=RATE_LIMIT_ERROR).with_structured_output(DummyOutput)

        with pytest.raises(ValueError, match="chave inválida"):
            invoke_llm_with_retry(primary, MESSAGES, output_schema=DummyOutput)
