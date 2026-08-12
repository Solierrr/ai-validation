"""
Nó de consolidação determinístico (sem LLM).

Este é o último nó da pipeline. Recebe os resultados dos agentes especialistas
e aplica regras de negócio determinísticas para tomar a decisão final:
- Verifica se o security guardrail aprovou
- Valida expiração dos certificados (máx. 24 meses)
- Verifica carga horária mínima (NR-10: 20h, NR-35: 8h)
- Faz fuzzy matching dos nomes para garantir que ambos certificados
  pertencem ao mesmo profissional

A decisão é sempre ACCEPT ou REJECTED, sem margem para ambiguidade.
"""

from datetime import date, timedelta
from typing import Any, Dict

from rapidfuzz import fuzz

# Validade máxima dos certificados: 24 meses (aproximado como 730 dias)
MAX_CERTIFICATE_AGE_DAYS = 730


def consolidation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nó de consolidação — toma a decisão final de forma determinística.

    Pipeline de verificação (em ordem de prioridade):
    1. Security check → se is_safe=false → REJECTED
    2. NR-10 válido? → se valid=false → REJECTED
    3. NR-10 expirado? → se > 24 meses → REJECTED
    4. NR-10 carga horária → se < 20h → REJECTED
    5. NR-35 válido? → se valid=false → REJECTED
    6. NR-35 expirado? → se > 24 meses → REJECTED
    7. NR-35 carga horária → se < 8h → REJECTED
    8. Nomes extraídos? → se vazio → REJECTED
    9. Fuzzy name match → se similaridade < 85% → REJECTED
    10. Tudo OK → ACCEPT
    """

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. VERIFICAÇÃO DE SEGURANÇA
    # Se o guardrail detectou risco (prompt injection, doc ilegível, etc.),
    # rejeita imediatamente sem verificar os certificados.
    # ═══════════════════════════════════════════════════════════════════════════
    if not state.get("is_safe", False):
        return {
            "status": "REJECTED",
            "error_code": state.get("security_error_code", "SECURITY_RISK"),
            "reason": state.get(
                "security_reason",
                "Risco de segurança detectado no documento.",
            ),
        }

    # Obtém os resultados dos agentes (dicts com valid, student_name, etc.)
    nr10 = state.get("nr10_result", {}) or {}
    nr35 = state.get("nr35_result", {}) or {}

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. VALIDAÇÃO DO CERTIFICADO NR-10
    # Verifica se o agente NR-10 considerou o certificado válido.
    # ═══════════════════════════════════════════════════════════════════════════
    if not nr10.get("valid", False):
        return {
            "status": "REJECTED",
            "error_code": nr10.get("error_code", "INVALID_NR10"),
            "reason": f"Falha na NR-10: {nr10.get('error_reason', 'Erro desconhecido')}",
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. CHECK DE EXPIRAÇÃO NR-10 (máximo 24 meses)
    # Verificação determinística que não depende do LLM.
    # Se a issue_date está a mais de 730 dias da data atual, está expirado.
    # ═══════════════════════════════════════════════════════════════════════════
    current_date_str = state.get("current_date")
    if current_date_str:
        try:
            ref_date = date.fromisoformat(current_date_str)
            nr10_issue = nr10.get("issue_date")
            if nr10_issue:
                nr10_issue_date = date.fromisoformat(nr10_issue)
                if (ref_date - nr10_issue_date).days > MAX_CERTIFICATE_AGE_DAYS:
                    return {
                        "status": "REJECTED",
                        "error_code": "EXPIRED_CERTIFICATE",
                        "reason": (
                            f"O certificado NR-10 foi emitido em {nr10_issue} e está expirado "
                            f"(validade máxima de 24 meses em relação a {current_date_str})."
                        ),
                    }
        except (ValueError, TypeError):
            # Se o parsing da data falhar, confia na avaliação do LLM
            pass

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. CHECK DE CARGA HORÁRIA NR-10 (mínimo 20h)
    # NR-10 exige mínimo de 20h (reciclagem) ou 40h (formação).
    # Qualquer valor abaixo de 20h é automaticamente inválido.
    # ═══════════════════════════════════════════════════════════════════════════
    nr10_workload = nr10.get("workload_hours") or 0  # None → 0
    if nr10_workload < 20:
        return {
            "status": "REJECTED",
            "error_code": "INSUFFICIENT_WORKLOAD",
            "reason": (
                f"A NR-10 possui apenas {nr10_workload}h. "
                "A carga horária mínima exigida é de 20h (reciclagem) ou 40h (formação)."
            ),
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # 5. VALIDAÇÃO DO CERTIFICADO NR-35
    # ═══════════════════════════════════════════════════════════════════════════
    if not nr35.get("valid", False):
        return {
            "status": "REJECTED",
            "error_code": nr35.get("error_code", "INVALID_NR35"),
            "reason": f"Falha na NR-35: {nr35.get('error_reason', 'Erro desconhecido')}",
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # 6. CHECK DE EXPIRAÇÃO NR-35 (máximo 24 meses)
    # ═══════════════════════════════════════════════════════════════════════════
    if current_date_str:
        try:
            ref_date = date.fromisoformat(current_date_str)
            nr35_issue = nr35.get("issue_date")
            if nr35_issue:
                nr35_issue_date = date.fromisoformat(nr35_issue)
                if (ref_date - nr35_issue_date).days > MAX_CERTIFICATE_AGE_DAYS:
                    return {
                        "status": "REJECTED",
                        "error_code": "EXPIRED_CERTIFICATE",
                        "reason": (
                            f"O certificado NR-35 foi emitido em {nr35_issue} e está expirado "
                            f"(validade máxima de 24 meses em relação a {current_date_str})."
                        ),
                    }
        except (ValueError, TypeError):
            pass

    # ═══════════════════════════════════════════════════════════════════════════
    # 7. CHECK DE CARGA HORÁRIA NR-35 (mínimo 8h)
    # NR-35 exige mínimo de 8h para trabalho em altura.
    # ═══════════════════════════════════════════════════════════════════════════
    nr35_workload = nr35.get("workload_hours") or 0
    if nr35_workload < 8:
        return {
            "status": "REJECTED",
            "error_code": "INSUFFICIENT_WORKLOAD",
            "reason": (
                f"A NR-35 possui apenas {nr35_workload}h. "
                "A carga horária mínima exigida é de 8h."
            ),
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # 8. FUZZY NAME MATCHING (NR-10 vs NR-35)
    # Compara o nome do aluno extraído de ambos os certificados usando
    # token_set_ratio do RapidFuzz (tolerante a ordem e pequenas diferenças).
    # Threshold: 85% de similaridade — abaixo disso são considerados nomes diferentes.
    # ═══════════════════════════════════════════════════════════════════════════
    name_nr10 = (nr10.get("student_name") or "").strip().lower()
    name_nr35 = (nr35.get("student_name") or "").strip().lower()

    # Se não conseguiu extrair o nome de um ou ambos, rejeita
    if not name_nr10 or not name_nr35:
        return {
            "status": "REJECTED",
            "error_code": "MISSING_STUDENT_NAME",
            "reason": "Não foi possível extrair o nome do aluno em um ou ambos os certificados.",
        }

    # Calcula similaridade fuzzy (0-100) — token_set_ratio é robusto contra
    # variações de ordem das palavras e diferenças de casing
    similarity_score = fuzz.token_set_ratio(name_nr10, name_nr35)

    if similarity_score < 85:
        return {
            "status": "REJECTED",
            "error_code": "NAME_MISMATCH",
            "reason": (
                f"O nome no certificado de NR-10 ({nr10.get('student_name')}) "
                f"não corresponde ao nome no certificado de NR-35 ({nr35.get('student_name')})."
            ),
            "extracted_data": {
                "nr10_student_name": nr10.get("student_name"),
                "nr35_student_name": nr35.get("student_name"),
            },
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # 9. APROVAÇÃO FINAL
    # Todos os checks passaram — certificados válidos e do mesmo profissional.
    # Retorna ACCEPT com os dados extraídos para o cliente.
    # ═══════════════════════════════════════════════════════════════════════════
    return {
        "status": "ACCEPT",
        "error_code": None,
        "reason": (
            "Ambos os certificados possuem estrutura válida, carga horária adequada, "
            "estão no prazo de validade (24 meses) e pertencem ao mesmo profissional."
        ),
        "extracted_data": {
            "detected_student_name": nr10.get("student_name"),
            "nr10": {
                "valid": True,
                "institution_name": nr10.get("institution_name"),
                "workload_hours": nr10.get("workload_hours"),
                "issue_date": nr10.get("issue_date"),
                "has_required_structure": nr10.get("has_required_structure"),
            },
            "nr35": {
                "valid": True,
                "institution_name": nr35.get("institution_name"),
                "workload_hours": nr35.get("workload_hours"),
                "issue_date": nr35.get("issue_date"),
                "has_required_structure": nr35.get("has_required_structure"),
            },
        },
    }
