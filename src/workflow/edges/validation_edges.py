"""
Funções de roteamento condicional (edges) da pipeline de validação de certificados.
"""

from src.workflow.state import CertificateGraphState


def _check_security(state: CertificateGraphState) -> str:
    """
    Função de roteamento condicional após o security guardrail.

    Retorna:
        "continue" → segue para os agentes especialistas (NR-10 → NR-35)
        "reject"   → pula direto para consolidation (rejeição por segurança)
    """
    if state.get("is_safe", False):
        return "continue"
    return "reject"
