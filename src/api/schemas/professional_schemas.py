from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class ExpectedIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=60)
    cpf: str = Field(pattern=r"^\d{11}$")
    birthDate: date


class ExpectedRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    council: str = Field(min_length=1, max_length=60)
    number: str = Field(min_length=1, max_length=30)
    expiration: date | None = None


class ProfessionalDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    kind: Literal["IDENTITY", "REGISTRATION", "NR10", "NR35", "CERTIFICATE"]
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    readUrl: HttpUrl | None = None
    contentBase64: str | None = Field(default=None, max_length=14_000_000)
    contentType: str | None = None

    @model_validator(mode="after")
    def one_source(self):
        if (self.readUrl is None) == (self.contentBase64 is None):
            raise ValueError("Exactly one document source is required")
        return self


class ProfessionalValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    submissionId: UUID
    revision: int = Field(ge=1)
    policyVersion: int = Field(ge=1)
    professionId: UUID
    expectedIdentity: ExpectedIdentity
    expectedProfession: str = Field(min_length=1, max_length=100)
    expectedRegistration: ExpectedRegistration | None = None
    criteria: list[str] = Field(min_length=1, max_length=20)
    documents: list[ProfessionalDocument] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def unique_identifiers(self):
        if len(set(self.criteria)) != len(self.criteria):
            raise ValueError("Criteria must be unique")
        if len({document.id for document in self.documents}) != len(self.documents):
            raise ValueError("Document identifiers must be unique")
        return self


class CriterionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    result: Literal["PASSED", "FAILED", "INCONCLUSIVE"]
    reason: str = Field(min_length=1, max_length=2000)
    documentIds: list[UUID] = Field(default_factory=list)


class AgentAnalysis(BaseModel):
    safe: bool
    criteriaResults: list[CriterionResult]


class ProfessionalValidationResponse(BaseModel):
    submissionId: UUID
    revision: int
    policyVersion: int
    status: Literal["PASSED", "MANUAL_REVIEW"]
    criteriaResults: list[CriterionResult]
    validatorVersion: str = "professional-v1"
    completedAt: datetime
