"""
Schemas Pydantic para o endpoint de validação de CNPJ.

Define os modelos de request, response e output estruturado do LLM
para o fluxo de validação de empresas parceiras.
"""

from typing import Optional

from pydantic import BaseModel, Field


class CNPJValidationRequest(BaseModel):
    """Payload de entrada — recebe o CNPJ com ou sem formatação."""

    cnpj: str = Field(
        description="CNPJ da empresa parceira com ou sem formatação",
        examples=["12.345.678/0001-90", "12345678000190"],
    )


class CompanyLLMAuditOutput(BaseModel):
    """
    Schema de saída estruturada do agente de IA.

    O LLM retorna neste formato após analisar os CNAEs da empresa.
    """

    is_compatible: bool = Field(description="Indica se o ramo da empresa é aceito")
    category_label: str = Field(
        description="Categoria identificada (ex: ENGENHARIA_E_INSTALACOES, COMERCIO_ELETRO_ELETRONICO, INCOMPATIVEL)"
    )
    justification: str = Field(description="Justificativa sucinta sobre a decisão da IA")


class CNPJValidationResponse(BaseModel):
    """
    Payload de saída da API.

    Retorna o resultado final: VALID (empresa aprovada) ou INVALID (rejeitada).
    """

    status: str = Field(
        description="VALID ou INVALID",
        examples=["VALID", "INVALID"],
    )
    cnpj: str = Field(description="CNPJ sanitizado (apenas 14 dígitos)")
    company_name: Optional[str] = Field(default=None, description="Razão social oficial")
    trade_name: Optional[str] = Field(default=None, description="Nome fantasia")
    is_active: bool = Field(default=False, description="Se o CNPJ está ativo na Receita Federal")
    matched_category: Optional[str] = Field(
        default=None, description="Categoria compatível identificada pelo agente"
    )
    error_code: Optional[str] = Field(
        default=None, description="Código de erro padronizado em caso de rejeição"
    )
    reason: str = Field(description="Detalhamento amigável para exibição no app")
