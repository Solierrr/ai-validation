"""
Definição do estado global compartilhado entre todos os nós do LangGraph.

O CertificateGraphState é um TypedDict que funciona como a "memória" da pipeline.
Cada nó lê e escreve campos neste estado conforme processa sua etapa.
"""

from typing import Any, TypedDict


class CertificateGraphState(TypedDict):
    """
    Estado global do grafo de validação de certificados.

    Este TypedDict é passado entre todos os nós da pipeline LangGraph.
    Cada nó pode ler qualquer campo e adicionar seus resultados.
    """

    # ─── Inputs da API ───────────────────────────────────────────────────────
    cert_nr10_url: str  # URL da imagem do certificado NR-10 (fornecida pelo cliente)
    cert_nr35_url: str  # URL da imagem do certificado NR-35 (fornecida pelo cliente)
    current_date: (
        str  # Data de referência no formato YYYY-MM-DD (injetada automaticamente)
    )

    # ─── Cache de imagens (otimização) ───────────────────────────────────────
    # Preenchidos pelo security_guardrail após download, reutilizados pelos agentes
    # para evitar re-download das mesmas imagens (economia de latência e banda)
    cert_nr10_b64: str | None  # Imagem NR-10 em base64
    cert_nr10_mime: str | None  # MIME type da imagem NR-10 (ex: "image/jpeg")
    cert_nr35_b64: str | None  # Imagem NR-35 em base64
    cert_nr35_mime: str | None  # MIME type da imagem NR-35

    # ─── Controle do Security Guardrail ──────────────────────────────────────
    is_safe: bool  # True se os documentos passaram na verificação de segurança
    security_error_code: (
        str | None
    )  # Código de erro (ex: "SECURITY_RISK", "ILLEGIBLE_DOCUMENT")
    security_reason: str | None  # Razão da rejeição por segurança

    # ─── Resultados dos agentes especialistas ────────────────────────────────
    nr10_result: (
        dict[str, Any] | None
    )  # Output do NR-10 agent (valid, student_name, etc.)
    nr35_result: (
        dict[str, Any] | None
    )  # Output do NR-35 agent (valid, student_name, etc.)

    # ─── Decisão final consolidada ───────────────────────────────────────────
    status: str  # "ACCEPT" ou "REJECTED"
    reason: str  # Explicação legível do resultado
    error_code: str | None  # Código de erro padronizado (null se aprovado)
    extracted_data: (
        dict[str, Any] | None
    )  # Dados extraídos dos certificados (null se rejeitado)
