"""Testes do agente de segurança (src/workflow/nodes/security_guardrail_node.py)."""

import base64
from unittest.mock import MagicMock, patch

import pytest

from src.workflow.nodes.security_guardrail_node import (
    GuardrailOutput,
    _download_image,
    security_guardrail_node,
)

IMAGE_BYTES = b"fake-image-bytes"
EXPECTED_B64 = base64.b64encode(IMAGE_BYTES).decode("utf-8")

STATE = {
    "cert_nr10_url": "https://exemplo.com/nr10.jpg",
    "cert_nr35_url": "https://exemplo.com/nr35.png",
}


def _fake_response(content_type="image/png; charset=utf-8"):
    """Resposta HTTP fake com bytes de imagem."""
    response = MagicMock()
    response.content = IMAGE_BYTES
    response.headers = {"content-type": content_type} if content_type else {}
    response.raise_for_status.return_value = None
    return response


def _wire_client(mock_client_cls, response=None, error=None):
    """Configura o httpx.Client mockado para retornar resposta ou levantar erro."""
    client = mock_client_cls.return_value.__enter__.return_value
    if error is not None:
        client.get.side_effect = error
    else:
        client.get.return_value = response or _fake_response()


class TestDownloadImage:
    """Helper de download e conversão para base64."""

    @patch("src.workflow.nodes.security_guardrail_node.httpx.Client")
    def test_returns_base64_and_mime_type(self, mock_client_cls):
        _wire_client(mock_client_cls)

        b64, mime = _download_image("https://exemplo.com/img.png")

        assert b64 == EXPECTED_B64
        assert mime == "image/png"

    @patch("src.workflow.nodes.security_guardrail_node.httpx.Client")
    def test_defaults_to_jpeg_when_header_absent(self, mock_client_cls):
        _wire_client(mock_client_cls, response=_fake_response(content_type=None))

        _, mime = _download_image("https://exemplo.com/img")

        assert mime == "image/jpeg"

    @patch("src.workflow.nodes.security_guardrail_node.httpx.Client")
    def test_propagates_http_error(self, mock_client_cls):
        _wire_client(mock_client_cls, error=RuntimeError("404 not found"))

        with pytest.raises(RuntimeError):
            _download_image("https://exemplo.com/img")


@patch("src.workflow.nodes.security_guardrail_node.invoke_llm_with_retry")
@patch("src.workflow.nodes.security_guardrail_node.get_llm")
@patch("src.workflow.nodes.security_guardrail_node.httpx.Client")
class TestGuardrailNode:
    """Nó do security guardrail dentro da pipeline."""

    def test_returns_safe_and_caches_images(self, mock_client_cls, mock_get_llm, mock_invoke):
        _wire_client(mock_client_cls)
        mock_invoke.return_value = GuardrailOutput(
            is_safe=True, security_error_code=None, security_reason=None
        )

        result = security_guardrail_node(STATE)

        assert result["is_safe"] is True
        # As imagens baixadas ficam no state para os agentes reaproveitarem
        assert result["cert_nr10_b64"] == EXPECTED_B64
        assert result["cert_nr35_b64"] == EXPECTED_B64
        assert result["cert_nr10_mime"] == "image/png"
        assert result["cert_nr35_mime"] == "image/png"

    def test_downloads_both_certificates_once(self, mock_client_cls, mock_get_llm, mock_invoke):
        _wire_client(mock_client_cls)
        mock_invoke.return_value = GuardrailOutput(is_safe=True)

        security_guardrail_node(STATE)

        client = mock_client_cls.return_value.__enter__.return_value
        assert client.get.call_count == 2

    def test_propagates_llm_rejection(self, mock_client_cls, mock_get_llm, mock_invoke):
        _wire_client(mock_client_cls)
        mock_invoke.return_value = GuardrailOutput(
            is_safe=False,
            security_error_code="PROMPT_INJECTION",
            security_reason="Instrucao oculta detectada na imagem.",
        )

        result = security_guardrail_node(STATE)

        assert result["is_safe"] is False
        assert result["security_error_code"] == "PROMPT_INJECTION"
        assert "oculta" in result["security_reason"]

    def test_disables_groq_fallback_because_of_vision(
        self, mock_client_cls, mock_get_llm, mock_invoke
    ):
        """Groq não suporta imagens, então o fallback deve estar desligado."""
        _wire_client(mock_client_cls)
        mock_invoke.return_value = GuardrailOutput(is_safe=True)

        security_guardrail_node(STATE)

        assert mock_invoke.call_args.kwargs["allow_groq_fallback"] is False

    def test_sends_both_images_as_data_urls(self, mock_client_cls, mock_get_llm, mock_invoke):
        _wire_client(mock_client_cls)
        mock_invoke.return_value = GuardrailOutput(is_safe=True)

        security_guardrail_node(STATE)

        messages = mock_invoke.call_args.args[1]
        image_parts = [
            part for part in messages[1].content if part["type"] == "image_url"
        ]
        assert len(image_parts) == 2
        assert image_parts[0]["image_url"]["url"].startswith("data:image/png;base64,")

    def test_returns_illegible_document_when_download_fails(
        self, mock_client_cls, mock_get_llm, mock_invoke
    ):
        _wire_client(mock_client_cls, error=RuntimeError("connection refused"))

        result = security_guardrail_node(STATE)

        assert result["is_safe"] is False
        assert result["security_error_code"] == "ILLEGIBLE_DOCUMENT"
        assert result["cert_nr10_b64"] is None
        assert result["cert_nr35_b64"] is None
        mock_invoke.assert_not_called()

    def test_returns_security_risk_when_llm_fails(
        self, mock_client_cls, mock_get_llm, mock_invoke
    ):
        """Falha do LLM é tratada como risco (fail-safe)."""
        _wire_client(mock_client_cls)
        mock_invoke.side_effect = RuntimeError("todas as keys estouraram")

        result = security_guardrail_node(STATE)

        assert result["is_safe"] is False
        assert result["security_error_code"] == "SECURITY_RISK"
        assert "estouraram" in result["security_reason"]
