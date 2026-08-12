"""Testes da consolidação determinística (src/workflow/nodes/consolidation_node.py)."""

from src.workflow.nodes.consolidation_node import MAX_CERTIFICATE_AGE_DAYS, consolidation_node

# Data de referência usada nos testes de expiração
REFERENCE_DATE = "2026-07-15"


class TestSecurityRejection:
    """Etapa 1 — rejeição pelo security guardrail."""

    def test_rejects_when_not_safe(self):
        result = consolidation_node(
            {
                "is_safe": False,
                "security_error_code": "SECURITY_PROMPT_INJECTION",
                "security_reason": "Tentativa de prompt injection detectada.",
            }
        )

        assert result["status"] == "REJECTED"
        assert result["error_code"] == "SECURITY_PROMPT_INJECTION"
        assert "prompt injection" in result["reason"].lower()

    def test_uses_default_code_when_is_safe_missing(self):
        """Estado sem is_safe deve ser tratado como inseguro (fail-safe)."""
        result = consolidation_node({})

        assert result["status"] == "REJECTED"
        assert result["error_code"] == "SECURITY_RISK"
        assert "segurança" in result["reason"].lower()


class TestNR10Validation:
    """Etapas 2 a 4 — validação do certificado NR-10."""

    def test_rejects_invalid_nr10_with_agent_error_code(self):
        result = consolidation_node(
            {
                "is_safe": True,
                "nr10_result": {
                    "valid": False,
                    "error_code": "MISSING_STRUCTURE",
                    "error_reason": "Falta assinatura do responsável técnico.",
                },
            }
        )

        assert result["status"] == "REJECTED"
        assert result["error_code"] == "MISSING_STRUCTURE"
        assert "NR-10" in result["reason"]

    def test_uses_default_code_when_agent_omits_it(self):
        result = consolidation_node({"is_safe": True, "nr10_result": {"valid": False}})

        assert result["error_code"] == "INVALID_NR10"
        assert "Erro desconhecido" in result["reason"]

    def test_rejects_workload_below_minimum(self, valid_nr10_result):
        valid_nr10_result["workload_hours"] = 10
        result = consolidation_node(
            {"is_safe": True, "current_date": REFERENCE_DATE, "nr10_result": valid_nr10_result}
        )

        assert result["error_code"] == "INSUFFICIENT_WORKLOAD"
        assert "10h" in result["reason"]
        assert "20h" in result["reason"]

    def test_rejects_workload_none(self, valid_nr10_result):
        """workload_hours None deve ser tratado como 0 e rejeitado."""
        valid_nr10_result["workload_hours"] = None
        result = consolidation_node(
            {"is_safe": True, "current_date": REFERENCE_DATE, "nr10_result": valid_nr10_result}
        )

        assert result["error_code"] == "INSUFFICIENT_WORKLOAD"

    def test_accepts_workload_at_minimum(self, approved_state):
        """20h é o mínimo aceito para reciclagem de NR-10."""
        approved_state["nr10_result"]["workload_hours"] = 20
        result = consolidation_node(approved_state)

        assert result["status"] == "ACCEPT"


class TestNR35Validation:
    """Etapas 5 a 7 — validação do certificado NR-35."""

    def test_rejects_invalid_nr35_with_agent_error_code(self, valid_nr10_result):
        result = consolidation_node(
            {
                "is_safe": True,
                "current_date": REFERENCE_DATE,
                "nr10_result": valid_nr10_result,
                "nr35_result": {
                    "valid": False,
                    "error_code": "EXPIRED_CERTIFICATE",
                    "error_reason": "Certificado expirado.",
                },
            }
        )

        assert result["error_code"] == "EXPIRED_CERTIFICATE"
        assert "NR-35" in result["reason"]

    def test_uses_default_code_when_agent_omits_it(self, valid_nr10_result):
        result = consolidation_node(
            {
                "is_safe": True,
                "current_date": REFERENCE_DATE,
                "nr10_result": valid_nr10_result,
                "nr35_result": {"valid": False},
            }
        )

        assert result["error_code"] == "INVALID_NR35"

    def test_rejects_workload_below_minimum(self, approved_state):
        approved_state["nr35_result"]["workload_hours"] = 4
        result = consolidation_node(approved_state)

        assert result["error_code"] == "INSUFFICIENT_WORKLOAD"
        assert "4h" in result["reason"]
        assert "8h" in result["reason"]

    def test_rejects_workload_none(self, approved_state):
        approved_state["nr35_result"]["workload_hours"] = None
        result = consolidation_node(approved_state)

        assert result["error_code"] == "INSUFFICIENT_WORKLOAD"

    def test_accepts_workload_at_minimum(self, approved_state):
        """8h é o mínimo aceito para NR-35."""
        approved_state["nr35_result"]["workload_hours"] = 8
        result = consolidation_node(approved_state)

        assert result["status"] == "ACCEPT"


class TestExpirationCheck:
    """Verificação determinística de validade (24 meses / 730 dias)."""

    def test_constant_is_two_years(self):
        assert MAX_CERTIFICATE_AGE_DAYS == 730

    def test_rejects_expired_nr10(self, approved_state):
        # 731 dias antes da data de referência
        approved_state["nr10_result"]["issue_date"] = "2024-07-14"
        result = consolidation_node(approved_state)

        assert result["status"] == "REJECTED"
        assert result["error_code"] == "EXPIRED_CERTIFICATE"
        assert "NR-10" in result["reason"]

    def test_accepts_nr10_exactly_at_limit(self, approved_state):
        # Exatamente 730 dias antes: ainda dentro da validade
        approved_state["nr10_result"]["issue_date"] = "2024-07-15"
        result = consolidation_node(approved_state)

        assert result["status"] == "ACCEPT"

    def test_rejects_expired_nr35(self, approved_state):
        approved_state["nr35_result"]["issue_date"] = "2024-07-14"
        result = consolidation_node(approved_state)

        assert result["status"] == "REJECTED"
        assert result["error_code"] == "EXPIRED_CERTIFICATE"
        assert "NR-35" in result["reason"]

    def test_skips_check_when_current_date_missing(self, approved_state):
        """Sem current_date não há como calcular expiração — confia no agente."""
        approved_state.pop("current_date")
        approved_state["nr10_result"]["issue_date"] = "2010-01-01"
        result = consolidation_node(approved_state)

        assert result["status"] == "ACCEPT"

    def test_skips_check_when_issue_date_missing(self, approved_state):
        approved_state["nr10_result"]["issue_date"] = None
        result = consolidation_node(approved_state)

        assert result["status"] == "ACCEPT"

    def test_skips_check_when_date_is_malformed(self, approved_state):
        """Data em formato inesperado não deve quebrar a consolidação."""
        approved_state["nr10_result"]["issue_date"] = "15/01/2026"
        result = consolidation_node(approved_state)

        assert result["status"] == "ACCEPT"

    def test_skips_check_when_nr35_date_is_malformed(self, approved_state):
        approved_state["nr35_result"]["issue_date"] = "10-02-2026"
        result = consolidation_node(approved_state)

        assert result["status"] == "ACCEPT"

    def test_skips_check_when_nr35_issue_date_missing(self, approved_state):
        approved_state["nr35_result"]["issue_date"] = None
        result = consolidation_node(approved_state)

        assert result["status"] == "ACCEPT"


class TestNameMatching:
    """Etapa 8 — fuzzy matching do nome do profissional entre os certificados."""

    def test_rejects_when_nr10_name_missing(self, approved_state):
        approved_state["nr10_result"]["student_name"] = None
        result = consolidation_node(approved_state)

        assert result["error_code"] == "MISSING_STUDENT_NAME"

    def test_rejects_when_nr35_name_empty(self, approved_state):
        approved_state["nr35_result"]["student_name"] = ""
        result = consolidation_node(approved_state)

        assert result["error_code"] == "MISSING_STUDENT_NAME"

    def test_rejects_different_names(self, approved_state):
        approved_state["nr10_result"]["student_name"] = "EVERSON DE SOUZA LIMA"
        approved_state["nr35_result"]["student_name"] = "REGINALDO DE ARAUJO"
        result = consolidation_node(approved_state)

        assert result["status"] == "REJECTED"
        assert result["error_code"] == "NAME_MISMATCH"
        assert result["extracted_data"]["nr10_student_name"] == "EVERSON DE SOUZA LIMA"
        assert result["extracted_data"]["nr35_student_name"] == "REGINALDO DE ARAUJO"

    def test_accepts_names_with_case_and_spacing_variation(self, approved_state):
        """Variações de caixa e espaçamento do OCR não devem reprovar."""
        approved_state["nr10_result"]["student_name"] = "Carlos Eduardo da Silva"
        approved_state["nr35_result"]["student_name"] = "  CARLOS EDUARDO DA SILVA  "
        result = consolidation_node(approved_state)

        assert result["status"] == "ACCEPT"


class TestFullApproval:
    """Etapa 9 — payload de aprovação."""

    def test_returns_accept_with_extracted_data(self, approved_state):
        result = consolidation_node(approved_state)

        assert result["status"] == "ACCEPT"
        assert result["error_code"] is None

        data = result["extracted_data"]
        assert data["detected_student_name"] == "Carlos Eduardo da Silva"
        assert data["nr10"]["valid"] is True
        assert data["nr10"]["workload_hours"] == 40
        assert data["nr10"]["institution_name"] == "SENAI SP"
        assert data["nr10"]["issue_date"] == "2026-01-15"
        assert data["nr10"]["has_required_structure"] is True
        assert data["nr35"]["valid"] is True
        assert data["nr35"]["workload_hours"] == 8
        assert data["nr35"]["institution_name"] == "Engehall Treinamentos"

    def test_handles_none_agent_results_as_empty(self):
        """nr10_result/nr35_result None não devem causar exceção."""
        result = consolidation_node(
            {"is_safe": True, "nr10_result": None, "nr35_result": None}
        )

        assert result["status"] == "REJECTED"
        assert result["error_code"] == "INVALID_NR10"
