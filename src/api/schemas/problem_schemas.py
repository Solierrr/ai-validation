"""
Schema do contrato de erro (ProblemDetail) usado na documentação OpenAPI.

O corpo é montado por src/api/errors.py; este modelo só descreve o formato.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class ProblemFieldError(BaseModel):
    """Erro de um campo na validação da requisição."""

    field: str = Field(description="Campo com erro", examples=["cnpj"])
    errorCode: str = Field(
        description="Código estável do erro", examples=["VALIDATION_FAILED"]
    )
    detail: str = Field(
        description="Explicação para quem depura", examples=["Field required"]
    )


class ProblemDetail(BaseModel):
    """Corpo de todo erro HTTP (application/problem+json)."""

    type: str = Field(description="Sempre about:blank", examples=["about:blank"])
    title: str = Field(
        description="O mesmo valor de errorCode", examples=["VALIDATION_FAILED"]
    )
    status: int = Field(description="Código HTTP", examples=[422])
    errorCode: str = Field(
        description="Código estável do catálogo de erros",
        examples=["VALIDATION_FAILED"],
    )
    detail: str = Field(
        description="Explicação para quem depura, em português; o front não exibe",
        examples=["Erro de validação nos campos da requisição."],
    )
    instance: str = Field(
        description="Caminho da requisição",
        examples=["/api/v1/companies/validate-cnpj"],
    )
    timestamp: datetime = Field(description="Momento do erro, em UTC")
    traceId: str | None = Field(default=None, description="Id do trace, quando houver")
    errors: list[ProblemFieldError] | None = Field(
        default=None, description="Erros por campo, só em validação"
    )


PROBLEM_DESCRIPTIONS = {
    401: "Credencial ausente ou inválida",
    403: "Chamador sem permissão",
    422: "Corpo da requisição inválido",
    429: "Limite de requisições por IP atingido",
    500: "Erro interno inesperado",
    502: "Dependência externa fora do ar ou com resposta inválida",
}


def problem_responses(*statuses: int) -> dict:
    """Respostas de erro documentadas com o ProblemDetail."""
    return {
        status: {"model": ProblemDetail, "description": PROBLEM_DESCRIPTIONS[status]}
        for status in statuses
    }
