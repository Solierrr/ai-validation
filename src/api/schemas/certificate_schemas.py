"""
Schemas Pydantic para request e response da API.

Define os modelos de dados que validam o input do cliente e
estruturam o output retornado pela pipeline de validação.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, HttpUrl


class CertificateValidationRequest(BaseModel):
    """
    Payload de entrada para validação de certificados.

    O cliente envia as URLs públicas das imagens dos certificados NR-10 e NR-35.
    O Pydantic valida automaticamente que são URLs HTTP(S) válidas.
    """

    cert_nr10_url: HttpUrl = Field(
        description="URL da imagem do certificado NR-10",
        examples=["https://storage.meuapp.com/docs/nr10_document.jpg"],
    )
    cert_nr35_url: HttpUrl = Field(
        description="URL da imagem do certificado NR-35",
        examples=["https://storage.meuapp.com/docs/nr35_document.png"],
    )


class NRCertificateDetail(BaseModel):
    """
    Detalhe de um certificado individual na resposta.

    Contém os dados extraídos pelo agente especialista (NR-10 ou NR-35).
    """

    valid: bool  # Se o certificado passou em todas as validações
    institution_name: Optional[str] = None  # Nome da instituição emissora
    workload_hours: Optional[int] = None  # Carga horária do curso (em horas)
    issue_date: Optional[str] = None  # Data de emissão (YYYY-MM-DD)
    has_required_structure: Optional[bool] = None  # Se tem os 6 elementos obrigatórios


class ExtractedData(BaseModel):
    """
    Dados extraídos dos certificados quando a validação é bem-sucedida.

    Também utilizado para retornar detalhes em caso de NAME_MISMATCH.
    """

    detected_student_name: Optional[str] = None  # Nome do profissional identificado
    nr10: Optional[NRCertificateDetail] = None  # Dados do certificado NR-10
    nr35: Optional[NRCertificateDetail] = None  # Dados do certificado NR-35
    # Campos usados em caso de mismatch de nomes
    nr10_student_name: Optional[str] = None  # Nome extraído do NR-10
    nr35_student_name: Optional[str] = None  # Nome extraído do NR-35


class CertificateValidationResponse(BaseModel):
    """
    Payload de saída da validação de certificados.

    Retornado ao cliente com o resultado final da pipeline:
    - status: "ACCEPT" (aprovado) ou "REJECTED" (rejeitado)
    - reason: Explicação legível do resultado
    - error_code: Código padronizado de erro (null quando aprovado)
    - extracted_data: Dados extraídos dos certificados (null quando rejeitado)
    """

    status: str = Field(
        description="Resultado da validação: ACCEPT ou REJECTED",
        examples=["ACCEPT", "REJECTED"],
    )
    reason: str = Field(
        description="Explicação do resultado",
    )
    error_code: Optional[str] = Field(
        default=None,
        description="Código de erro padronizado em caso de rejeição",
    )
    extracted_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Dados extraídos dos certificados",
    )
