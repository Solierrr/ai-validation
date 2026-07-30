Markdown# 🏢 ESPECIFICAÇÃO DE IMPLEMENTAÇÃO: VALIDADOR DE COMPATIBILIDADE DE CNPJ (NOVO FLUXO DE EMPRESAS)

## 📌 1. Visão Geral do Sistema

Esta especificação define o contrato de API e o fluxo de negócios para validação de empresas parceiras (integradoras/vendedoras) que desejam se cadastrar na plataforma. 

A API recebe apenas os dígitos do **CNPJ**, realiza o enriquecimento de dados cadastrais consultando a base da Receita Federal (via API pública) e utiliza um **Agente de IA** para fazer uma análise semântica das atividades econômicas (CNAE Principal e Secundários) da empresa, aprovando apenas aquelas cujo ramo esteja relacionado a **Energia Solar, Engenharia Elétrica, Instalações, Obras ou Comércio Elétrico**.

---

## 🚀 2. Interface da API (Contrato de Entrada e Saída)

### Endpoint
`POST /api/v1/companies/validate-cnpj`

### Payload de Entrada (JSON)
```json
{
  "cnpj": "12.345.678/0001-90"
}
Payloads de Saída (JSON)Caso de Aprovação (VALID):JSON{
  "status": "VALID",
  "cnpj": "12345678000190",
  "company_name": "SOLAR ENERGY ENGENHARIA E INSTALACOES LTDA",
  "trade_name": "SOLAR ENERGY",
  "is_active": true,
  "matched_category": "ENGENHARIA_E_INSTALACOES_ELETRICAS",
  "reason": "Empresa ativa e com ramo de atividade plenamente compatível com o setor solar e elétrico."
}
Caso de Rejeição por Categoria Incompatível (INVALID):JSON{
  "status": "INVALID",
  "cnpj": "98765432000110",
  "company_name": "DROGARIA E FARMACIA CENTRAL LTDA",
  "trade_name": "FARMACIA CENTRAL",
  "is_active": true,
  "error_code": "INVALID_COMPANY_CATEGORY",
  "reason": "A empresa está ativa, mas seu ramo de atividade (Comércio varejista de produtos farmacêuticos) não possui qualquer vínculo com energia solar, engenharia ou instalações elétricas."
}
Caso de Rejeição por CNPJ Inativo ou Inexistente (INVALID):JSON{
  "status": "INVALID",
  "cnpj": "11222333000199",
  "company_name": null,
  "trade_name": null,
  "is_active": false,
  "error_code": "CNPJ_INACTIVE",
  "reason": "O CNPJ informado não está ativo na Receita Federal (Situação: BAIXADA/INAPTA)."
}
🔄 3. Fluxo de Processamento (Passo a Passo)       [ Input: CNPJ ]
              │
              ▼
 ┌──────────────────────────┐
 │ 1. Sanitização de Texto  │ ➔ Remove caracteres especiais (pontos, traços, barras)
 └────────────┬─────────────┘
              │
              ▼
 ┌──────────────────────────┐
 │ 2. Consulta Externa      │ ➔ Requisita a BrasilAPI ([https://brasilapi.com.br/api/cnpj/v1/](https://brasilapi.com.br/api/cnpj/v1/){cnpj})
 └────────────┬─────────────┘
              │
     [ CNPJ Existe e está ATIVO? ]
      ├── NÃO ──► [ Retorna INVALID: CNPJ_NOT_FOUND ou CNPJ_INACTIVE ]
      └── SIM
              │
              ▼
 ┌──────────────────────────┐
 │ 3. Montagem do Payload   │ ➔ Agrupa Razão Social, CNAE Principal e CNAEs Secundários
 └────────────┬─────────────┘
              │
              ▼
 ┌──────────────────────────┐
 │ 4. Agente de IA (LLM)    │ ➔ Avalia se a descrição das atividades é compatível
 └────────────┬─────────────┘
              │
     [ Atividade Aprovada? ]
      ├── NÃO ──► [ Retorna INVALID: INVALID_COMPANY_CATEGORY ]
      └── SIM ──► [ Retorna VALID ]
🤖 4. Prompt de Sistema do Agente Auditor de CNPJEste prompt deve ser enviado para o modelo de IA junto com a lista de CNAEs extraída da Receita Federal:PlaintextVocê é um auditor corporativo especializado no mercado de energia e engenharia no Brasil.
Sua missão é determinar se a empresa analisada possui autorização/ramo de atividade compatível para atuar na venda, projeto, instalação, manutenção ou suporte de sistemas de energia solar fotovoltaica e elétrica.

DADOS DA EMPRESA (EXTRAÍDOS DA RECEITA FEDERAL):
- Razão Social: {{razao_social}}
- Nome Fantasia: {{nome_fantasia}}
- CNAE Principal: {{cnae_principal_codigo}} - {{cnae_principal_descricao}}
- CNAEs Secundários: 
{{lista_cnaes_secundarios_formatada}}

REGRAS DE AVALIAÇÃO:
1. APROVE (is_compatible = true) se a empresa possuir pelo menos UMA atividade relacionada a:
   - Energia Solar, Fotovoltaica ou Fontes Renováveis.
   - Engenharia (Elétrica, Civil, Mecânica ou Geral).
   - Instalações, Montagens, Manutenção Elétrica ou Hidráulica.
   - Comércio (Atacadista ou Varejista) de Materiais Eléticos, Equipamentos Eletrônicos, Máquinas ou Ferramentas.
   - Serviços de Arquitetura, Climatização, Refrigeração ou Obras de Alvenaria/Telhado.
   - Treinamentos Técnicos ou Desenvolvimento Profissional.

2. REJEITE (is_compatible = false) se a empresa for exclusivamente de ramos sem correlação técnica, tais como:
   - Alimentação (Lanchonetes, Restaurantes, Padarias, Bares).
   - Saúde, Odontologia e Farmácias.
   - Vestuário, Calçados e Beleza.
   - Transporte de Passageiros, Pet Shops, Supermercados ou Consultorias Jurídicas/Contábeis puras.

RESPOSTA ESPERADA (JSON STRICT):
{
  "is_compatible": boolean,
  "category_label": string, // ex: "ENGENHARIA_E_INSTALACOES", "COMERCIO_ELETRO_ELETRONICO", "INCOMPATIVEL"
  "justification": string  // Explicação clara de 1 a 2 frases
}
🏷️ 5. Tabela de Códigos de Erro Padronizados (error_code)CodeDescriçãoINVALID_CNPJ_FORMATO CNPJ fornecido não possui 14 dígitos válidos após a limpeza dos caracteres.CNPJ_NOT_FOUNDO CNPJ não foi localizado na base de dados da Receita Federal.CNPJ_INACTIVEO CNPJ existe, mas sua situação cadastral é diferente de "ATIVA" (ex: Baixada, Suspensa, Cancelada).INVALID_COMPANY_CATEGORYO CNPJ está ativo, mas suas atividades (CNAEs) não possuem relação com o setor solar/elétrico/engenharia.💻 6. Estrutura dos Schemas Pydantic (Python / FastAPI)Pythonfrom pydantic import BaseModel, Field
from typing import Optional

# Request Entrada
class CNPJValidationRequest(BaseModel):
    cnpj: str = Field(description="CNPJ da empresa parceira com ou sem formatação", example="12.345.678/0001-90")

# Resposta Estruturada da IA
class CompanyLLMAuditOutput(BaseModel):
    is_compatible: bool = Field(description="Indica se o ramo da empresa é aceito")
    category_label: str = Field(description="Categoria identificada para a empresa")
    justification: str = Field(description="Justificativa sucinta sobre a decisão da IA")

# Response Saída da API
class CNPJValidationResponse(BaseModel):
    status: str = Field(description="VALID ou INVALID")
    cnpj: str = Field(description="CNPJ sanitizado (apenas números)")
    company_name: Optional[str] = Field(default=None, description="Razão social oficial")
    trade_name: Optional[str] = Field(default=None, description="Nome fantasia")
    is_active: bool = Field(default=False)
    matched_category: Optional[str] = Field(default=None)
    error_code: Optional[str] = Field(default=None)
    reason: str = Field(description="Detalhamento amigável para exibição no app")