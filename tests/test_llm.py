"""Testes do módulo de LLM e da cadeia de fallback (src/core/llm.py)."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from src.core.llm import (
    _is_rate_limit_error,
    get_groq_llm,
    get_llm,
    invoke_llm_with_retry,
)


class DummyOutput(BaseModel):
    """Schema simples usado como output_schema nos testes."""

    ok: bool = True


# Erro que simula estouro de cota (o que o Gemini/Groq retornam com HTTP 429)
RATE_LIMIT_ERROR = Exception("429 RESOURCE_EXHAUSTED: quota exceeded")

MESSAGES = [{"role": "user", "content": "analise isso"}]


def _mock_llm(result=None, error=None):
    """
    Cria um LLM fake.

    Se `error` for informado, tanto .invoke() quanto o structured output
    levantam esse erro. Caso contrário, retornam `result`.
    """
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


class TestGetLlm:
    """Factory do cliente Gemini."""

    @patch("src.core.llm.ChatGoogleGenerativeAI")
    def test_uses_primary_key_and_settings_by_default(self, mock_gemini):
        get_llm()

        kwargs = mock_gemini.call_args.kwargs
        assert kwargs["google_api_key"] == "test-gemini-key-1"
        assert kwargs["model"] == "gemini-2.5-flash"
        assert kwargs["temperature"] == 0.0
        assert kwargs["timeout"] == 60

    @patch("src.core.llm.ChatGoogleGenerativeAI")
    def test_explicit_api_key_overrides_settings(self, mock_gemini):
        get_llm(api_key="chave-alternativa")

        assert mock_gemini.call_args.kwargs["google_api_key"] == "chave-alternativa"


class TestGetGroqLlm:
    """Factory do cliente Groq (fallback)."""

    @patch("src.core.llm.ChatGroq")
    def test_uses_primary_groq_key_by_default(self, mock_groq):
        get_groq_llm()

        kwargs = mock_groq.call_args.kwargs
        assert kwargs["api_key"] == "test-groq-key-1"
        assert kwargs["model"] == "llama-3.3-70b-versatile"
        assert kwargs["timeout"] == 60

    @patch("src.core.llm.ChatGroq")
    def test_explicit_api_key_overrides_settings(self, mock_groq):
        get_groq_llm(api_key="groq-alternativa")

        assert mock_groq.call_args.kwargs["api_key"] == "groq-alternativa"


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
    """Comportamento da primeira tentativa (chave Gemini principal)."""

    def test_returns_result_from_primary_key(self):
        primary = _mock_llm(result="resultado-ok").with_structured_output(DummyOutput)

        assert invoke_llm_with_retry(primary, MESSAGES) == "resultado-ok"

    @patch("src.core.llm.get_llm")
    def test_does_not_fallback_when_error_is_not_rate_limit(self, mock_get_llm):
        """Erro que não é de cota deve propagar sem consumir chaves extras."""
        primary = _mock_llm(error=ValueError("modelo inexistente")).with_structured_output(
            DummyOutput
        )

        with pytest.raises(ValueError, match="modelo inexistente"):
            invoke_llm_with_retry(primary, MESSAGES, output_schema=DummyOutput)

        mock_get_llm.assert_not_called()


class TestGeminiFallback:
    """Fallback entre as chaves Gemini quando há estouro de cota."""

    @patch("src.core.llm.get_llm")
    def test_falls_back_to_second_gemini_key(self, mock_get_llm):
        mock_get_llm.return_value = _mock_llm(result="ok-key2")
        primary = _mock_llm(error=RATE_LIMIT_ERROR).with_structured_output(DummyOutput)

        result = invoke_llm_with_retry(primary, MESSAGES, output_schema=DummyOutput)

        assert result == "ok-key2"
        mock_get_llm.assert_called_once_with(api_key="test-gemini-key-2")

    @patch("src.core.llm.get_llm")
    def test_falls_back_to_third_gemini_key(self, mock_get_llm):
        """Se a chave 2 também estourar, deve tentar a chave 3."""
        mock_get_llm.side_effect = [
            _mock_llm(error=RATE_LIMIT_ERROR),
            _mock_llm(result="ok-key3"),
        ]
        primary = _mock_llm(error=RATE_LIMIT_ERROR).with_structured_output(DummyOutput)

        result = invoke_llm_with_retry(primary, MESSAGES, output_schema=DummyOutput)

        assert result == "ok-key3"
        assert mock_get_llm.call_count == 2

    @patch("src.core.llm.get_llm")
    def test_propagates_non_rate_limit_error_from_fallback(self, mock_get_llm):
        mock_get_llm.return_value = _mock_llm(error=ValueError("chave inválida"))
        primary = _mock_llm(error=RATE_LIMIT_ERROR).with_structured_output(DummyOutput)

        with pytest.raises(ValueError, match="chave inválida"):
            invoke_llm_with_retry(primary, MESSAGES, output_schema=DummyOutput)

    @patch("src.core.llm.get_llm")
    def test_invokes_llm_directly_when_no_output_schema(self, mock_get_llm):
        """Sem output_schema, o fallback usa o LLM cru (sem structured output)."""
        fallback = _mock_llm(result="ok-cru")
        mock_get_llm.return_value = fallback
        primary = _mock_llm(error=RATE_LIMIT_ERROR)

        result = invoke_llm_with_retry(primary, MESSAGES)

        assert result == "ok-cru"
        fallback.with_structured_output.assert_not_called()


@patch("src.core.llm.get_groq_llm")
@patch("src.core.llm.get_llm")
class TestGroqFallback:
    """Fallback para o Groq depois que todas as chaves Gemini estouram."""

    def test_uses_groq_when_all_gemini_keys_exhausted(self, mock_get_llm, mock_get_groq):
        mock_get_llm.return_value = _mock_llm(error=RATE_LIMIT_ERROR)
        mock_get_groq.return_value = _mock_llm(result="ok-groq")
        primary = _mock_llm(error=RATE_LIMIT_ERROR).with_structured_output(DummyOutput)

        result = invoke_llm_with_retry(primary, MESSAGES, output_schema=DummyOutput)

        assert result == "ok-groq"
        mock_get_groq.assert_called_once_with(api_key="test-groq-key-1")

    def test_falls_back_to_second_groq_key(self, mock_get_llm, mock_get_groq):
        mock_get_llm.return_value = _mock_llm(error=RATE_LIMIT_ERROR)
        mock_get_groq.side_effect = [
            _mock_llm(error=RATE_LIMIT_ERROR),
            _mock_llm(result="ok-groq2"),
        ]
        primary = _mock_llm(error=RATE_LIMIT_ERROR).with_structured_output(DummyOutput)

        result = invoke_llm_with_retry(primary, MESSAGES, output_schema=DummyOutput)

        assert result == "ok-groq2"
        assert mock_get_groq.call_count == 2

    def test_skips_groq_for_vision_calls(self, mock_get_llm, mock_get_groq):
        """Chamadas com imagem passam allow_groq_fallback=False (Groq não tem Vision)."""
        mock_get_llm.return_value = _mock_llm(error=RATE_LIMIT_ERROR)
        primary = _mock_llm(error=RATE_LIMIT_ERROR).with_structured_output(DummyOutput)

        with pytest.raises(Exception, match="rate limit"):
            invoke_llm_with_retry(
                primary,
                MESSAGES,
                output_schema=DummyOutput,
                allow_groq_fallback=False,
            )

        mock_get_groq.assert_not_called()

    def test_raises_when_every_provider_is_exhausted(self, mock_get_llm, mock_get_groq):
        mock_get_llm.return_value = _mock_llm(error=RATE_LIMIT_ERROR)
        mock_get_groq.return_value = _mock_llm(error=RATE_LIMIT_ERROR)
        primary = _mock_llm(error=RATE_LIMIT_ERROR).with_structured_output(DummyOutput)

        with pytest.raises(Exception, match="rate limit"):
            invoke_llm_with_retry(primary, MESSAGES, output_schema=DummyOutput)

    def test_propagates_non_rate_limit_error_from_groq(self, mock_get_llm, mock_get_groq):
        mock_get_llm.return_value = _mock_llm(error=RATE_LIMIT_ERROR)
        mock_get_groq.return_value = _mock_llm(error=ValueError("groq indisponível"))
        primary = _mock_llm(error=RATE_LIMIT_ERROR).with_structured_output(DummyOutput)

        with pytest.raises(ValueError, match="groq indisponível"):
            invoke_llm_with_retry(primary, MESSAGES, output_schema=DummyOutput)

    def test_invokes_groq_directly_when_no_output_schema(self, mock_get_llm, mock_get_groq):
        """Sem output_schema, o Groq é chamado sem structured output."""
        mock_get_llm.return_value = _mock_llm(error=RATE_LIMIT_ERROR)
        groq = _mock_llm(result="ok-groq-cru")
        mock_get_groq.return_value = groq
        primary = _mock_llm(error=RATE_LIMIT_ERROR)

        result = invoke_llm_with_retry(primary, MESSAGES)

        assert result == "ok-groq-cru"
        groq.with_structured_output.assert_not_called()
