from unittest.mock import patch
from uuid import uuid4

from src.api.schemas.professional_schemas import (
    AgentAnalysis,
    CriterionResult,
    ProfessionalValidationRequest,
)
from src.services.professional_validation import consolidate


def payload():
    return {
        "submissionId": str(uuid4()),
        "revision": 1,
        "policyVersion": 1,
        "professionId": str(uuid4()),
        "expectedProfession": "Instalador",
        "expectedIdentity": {
            "name": "Carlos Silva",
            "cpf": "12345678901",
            "birthDate": "1990-01-01",
        },
        "criteria": ["IDENTITY_MATCH"],
        "documents": [
            {
                "id": str(uuid4()),
                "kind": "IDENTITY",
                "sha256": "a" * 64,
                "readUrl": "https://storage.example.test/identity.png",
            }
        ],
    }


def test_service_authentication_required(client, monkeypatch):
    monkeypatch.setenv("VALIDATION_SERVICE_TOKEN", "x" * 32)
    assert (
        client.post("/api/v1/professionals/validate", json=payload()).status_code == 401
    )


def test_unknown_criteria_go_to_review(client, monkeypatch):
    monkeypatch.setenv("VALIDATION_SERVICE_TOKEN", "x" * 32)
    body = payload()
    body["criteria"] = ["UNKNOWN"]
    response = client.post(
        "/api/v1/professionals/validate",
        json=body,
        headers={"Authorization": "Bearer " + "x" * 32},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "MANUAL_REVIEW"


def test_missing_or_duplicate_result_cannot_approve():
    body = ProfessionalValidationRequest.model_validate(payload())
    result = CriterionResult(
        code="IDENTITY_MATCH",
        result="PASSED",
        reason="Matched",
        documentIds=[body.documents[0].id],
    )
    assert (
        consolidate(body, AgentAnalysis(safe=True, criteriaResults=[])).status
        == "MANUAL_REVIEW"
    )
    assert (
        consolidate(
            body, AgentAnalysis(safe=True, criteriaResults=[result, result])
        ).status
        == "MANUAL_REVIEW"
    )
    assert (
        consolidate(body, AgentAnalysis(safe=True, criteriaResults=[result])).status
        == "PASSED"
    )
    assert (
        consolidate(body, AgentAnalysis(safe=False, criteriaResults=[result])).status
        == "MANUAL_REVIEW"
    )


def test_failure_is_not_document_rejection(client, monkeypatch):
    monkeypatch.setenv("VALIDATION_SERVICE_TOKEN", "x" * 32)
    with patch(
        "src.api.routes.professional_routes.validate_professional",
        side_effect=RuntimeError(),
    ):
        response = client.post(
            "/api/v1/professionals/validate",
            json=payload(),
            headers={"Authorization": "Bearer " + "x" * 32},
        )
    assert response.status_code == 503


def test_evidence_for_a_different_kind_cannot_approve():
    body = ProfessionalValidationRequest.model_validate(payload())
    body.criteria = ["NR10"]
    result = CriterionResult(
        code="NR10",
        result="PASSED",
        reason="Claimed pass",
        documentIds=[body.documents[0].id],
    )
    assert (
        consolidate(body, AgentAnalysis(safe=True, criteriaResults=[result])).status
        == "MANUAL_REVIEW"
    )


def test_inline_document_must_match_its_hash():
    import base64
    import hashlib

    import pytest
    from fastapi import HTTPException

    from src.api.schemas.professional_schemas import ProfessionalDocument
    from src.services.professional_validation import download_document

    content = b"\x89PNG\r\n\x1a\n" + b"test"
    document = ProfessionalDocument(
        id=uuid4(),
        kind="IDENTITY",
        sha256=hashlib.sha256(content).hexdigest(),
        contentBase64=base64.b64encode(content).decode(),
        contentType="image/png",
    )
    assert download_document(document)[1] == "image/png"
    document.sha256 = "a" * 64
    with pytest.raises(HTTPException) as failure:
        download_document(document)
    assert failure.value.status_code == 422


def test_private_addresses_are_rejected_before_downloading(monkeypatch):
    import pytest
    from fastapi import HTTPException

    from src.services.professional_validation import download_document

    monkeypatch.setenv("VALIDATION_DOCUMENT_HOSTS", "storage.example.test")
    monkeypatch.setattr(
        "src.services.professional_validation.socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))],
    )
    with pytest.raises(HTTPException) as failure:
        download_document(
            ProfessionalValidationRequest.model_validate(payload()).documents[0]
        )
    assert failure.value.status_code == 422
