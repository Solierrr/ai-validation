"""Testes dos contratos de request/response (src/api/schemas/certificate_schemas.py e cnpj_schemas.py)."""

import pytest
from pydantic import ValidationError

from src.api.schemas.cnpj_schemas import (
    CNPJValidationRequest,
    CNPJValidationResponse,
    CompanyLLMAuditOutput,
)
from src.api.schemas.certificate_schemas import (
    CertificateValidationRequest,
    CertificateValidationResponse,
    ExtractedData,
    NRCertificateDetail,
)


class TestCertificateRequest:
    """Entrada da validação de certificados."""

    def test_accepts_valid_urls(self):
        request = CertificateValidationRequest(
            cert_nr10_url="https://exemplo.com/nr10.jpg",
            cert_nr35_url="https://exemplo.com/nr35.png",
        )

        assert str(request.cert_nr10_url) == "https://exemplo.com/nr10.jpg"

    def test_rejects_non_url_value(self):
        with pytest.raises(ValidationError):
            CertificateValidationRequest(cert_nr10_url="abc", cert_nr35_url="def")

    def test_requires_both_urls(self):
        with pytest.raises(ValidationError):
            CertificateValidationRequest(cert_nr10_url="https://exemplo.com/a.jpg")


class TestCertificateResponse:
    """Saída da validação de certificados."""

    def test_optional_fields_default_to_none(self):
        response = CertificateValidationResponse(status="ACCEPT", reason="ok")

        assert response.error_code is None
        assert response.extracted_data is None

    def test_carries_extracted_data(self):
        response = CertificateValidationResponse(
            status="ACCEPT", reason="ok", extracted_data={"detected_student_name": "Ana"}
        )

        assert response.extracted_data["detected_student_name"] == "Ana"


class TestCertificateDetailModels:
    """Modelos auxiliares que descrevem o extracted_data."""

    def test_detail_requires_valid_flag(self):
        detail = NRCertificateDetail(valid=True, workload_hours=40)

        assert detail.valid is True
        assert detail.workload_hours == 40
        assert detail.institution_name is None

    def test_extracted_data_supports_both_certificates(self):
        data = ExtractedData(
            detected_student_name="Ana",
            nr10=NRCertificateDetail(valid=True),
            nr35=NRCertificateDetail(valid=True),
        )

        assert data.nr10.valid is True
        assert data.nr35.valid is True

    def test_extracted_data_supports_name_mismatch_fields(self):
        data = ExtractedData(nr10_student_name="Ana", nr35_student_name="Bruno")

        assert data.nr10_student_name == "Ana"
        assert data.nr35_student_name == "Bruno"


class TestCnpjRequest:
    """Entrada da validação de CNPJ — aceita com ou sem formatação."""

    @pytest.mark.parametrize("value", ["12.345.678/0001-90", "12345678000190"])
    def test_accepts_formatted_and_raw(self, value):
        assert CNPJValidationRequest(cnpj=value).cnpj == value

    def test_requires_cnpj(self):
        with pytest.raises(ValidationError):
            CNPJValidationRequest()


class TestCnpjResponse:
    """Saída da validação de CNPJ."""

    def test_defaults_are_safe(self):
        """Por padrão a empresa não é considerada ativa (fail-safe)."""
        response = CNPJValidationResponse(status="INVALID", cnpj="123", reason="erro")

        assert response.is_active is False
        assert response.company_name is None
        assert response.trade_name is None
        assert response.matched_category is None
        assert response.error_code is None

    def test_serializes_approved_payload(self):
        response = CNPJValidationResponse(
            status="VALID",
            cnpj="12345678000190",
            company_name="SOLAR ENERGY LTDA",
            trade_name="SOLAR",
            is_active=True,
            matched_category="ENGENHARIA_E_INSTALACOES",
            reason="Compativel.",
        )

        body = response.model_dump()
        assert body["status"] == "VALID"
        assert body["is_active"] is True
        assert body["error_code"] is None


class TestCompanyAuditOutput:
    """Schema de saída estruturada exigido do LLM."""

    def test_requires_all_fields(self):
        with pytest.raises(ValidationError):
            CompanyLLMAuditOutput(is_compatible=True)

    def test_builds_complete_verdict(self):
        output = CompanyLLMAuditOutput(
            is_compatible=False,
            category_label="INCOMPATIVEL",
            justification="Ramo alimenticio.",
        )

        assert output.is_compatible is False
        assert output.category_label == "INCOMPATIVEL"
