"""Schemas das rotas de saúde (/health e /ready)."""

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Estado do serviço."""

    status: str = Field(description="UP ou DOWN", examples=["UP"])
    version: str | None = Field(
        default=None, description="Versão do release, só no /health", examples=["3.1.0"]
    )
