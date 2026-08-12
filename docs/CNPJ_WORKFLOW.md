# Fluxo de Validacao de CNPJ — AI Validation Platform

## Visao Geral

Este fluxo valida se uma empresa parceira (integradora/vendedora) possui
atividades economicas compativeis com o setor de energia solar e eletrica.

A API recebe um CNPJ, enriquece os dados via Receita Federal (BrasilAPI)
e utiliza um agente de IA para analisar semanticamente os CNAEs da empresa.

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                       API FastAPI                            │
│          POST /api/v1/companies/validate-cnpj               │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                   Fluxo de Validacao                        │
│                                                             │
│   ┌────────────────────┐                                    │
│   │ 1. Sanitizacao     │ ← Remove pontos, tracos, barras    │
│   │    do CNPJ         │   Valida se tem 14 digitos         │
│   └────────┬───────────┘                                    │
│            │                                                │
│            ▼                                                │
│   ┌────────────────────┐                                    │
│   │ 2. Consulta        │ ← BrasilAPI (Receita Federal)      │
│   │    Externa         │   GET /api/cnpj/v1/{cnpj}          │
│   └────────┬───────────┘                                    │
│            │                                                │
│       CNPJ existe?                                          │
│       /         \                                           │
│     NAO         SIM                                         │
│      │           │                                          │
│      ▼           ▼                                          │
│  INVALID    Esta ATIVO?                                     │
│  NOT_FOUND  /         \                                     │
│           NAO         SIM                                   │
│            │           │                                    │
│            ▼           ▼                                    │
│        INVALID    ┌────────────────────┐                    │
│        INACTIVE   │ 3. Agente de IA    │                    │
│                   │    (LLM Gemini)    │                    │
│                   │    Analisa CNAEs   │                    │
│                   └────────┬───────────┘                    │
│                            │                                │
│                     Compativel?                             │
│                     /         \                             │
│                   SIM         NAO                           │
│                    │           │                            │
│                    ▼           ▼                            │
│                 VALID      INVALID                          │
│                         COMPANY_CATEGORY                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Detalhamento das Etapas

### 1. Sanitizacao do CNPJ

**Arquivo:** `src/api/routes/cnpj_routes.py` (`_sanitize_cnpj`)

- Remove todos os caracteres nao-numericos (pontos, tracos, barras, espacos).
- Valida que o resultado tem exatamente 14 digitos.
- Se invalido, retorna `INVALID_CNPJ_FORMAT` imediatamente.

**Exemplo:**
```
"12.345.678/0001-90"  →  "12345678000190"  (14 digitos ✓)
"123"                 →  "123"             (3 digitos ✗)
```

---

### 2. Consulta a BrasilAPI

**Arquivo:** `src/services/brasil_api.py`

- Endpoint externo: `https://brasilapi.com.br/api/cnpj/v1/{cnpj}`
- Timeout: 15 segundos
- Retorna dados cadastrais completos da Receita Federal

**Dados utilizados:**
| Campo | Uso |
|-------|-----|
| `razao_social` | Nome oficial da empresa |
| `nome_fantasia` | Nome comercial |
| `descricao_situacao_cadastral` | Verifica se esta "ATIVA" |
| `cnae_fiscal` + `cnae_fiscal_descricao` | CNAE principal |
| `cnaes_secundarios` | Lista de CNAEs secundarios |

**Cenarios de erro:**
- HTTP 404 → CNPJ nao encontrado (`CNPJ_NOT_FOUND`)
- Outros erros HTTP → HTTP 502 para o cliente

---

### 3. Verificacao de Situacao Cadastral

**Arquivo:** `src/api/routes/cnpj_routes.py`

Verifica se `descricao_situacao_cadastral` == `"ATIVA"`.

Situacoes que resultam em rejeicao:
- BAIXADA
- SUSPENSA
- INAPTA
- CANCELADA
- NULA

---

### 4. Agente de IA (Analise de CNAEs)

**Arquivo:** `src/agents/specialist/cnpj_agent/cnpj_agent.py`

O agente recebe os dados da empresa (razao social, nome fantasia, CNAE principal
e CNAEs secundarios) e determina se o ramo de atividade e compativel.

**Categorias aprovadas:**
- Energia Solar, Fotovoltaica ou Fontes Renovaveis
- Engenharia (Eletrica, Civil, Mecanica ou Geral)
- Instalacoes, Montagens, Manutencao Eletrica ou Hidraulica
- Comercio de Materiais Eletricos, Equipamentos, Maquinas
- Arquitetura, Climatizacao, Refrigeracao, Obras
- Treinamentos Tecnicos ou Desenvolvimento Profissional

**Categorias rejeitadas:**
- Alimentacao (Lanchonetes, Restaurantes, Padarias)
- Saude, Odontologia e Farmacias
- Vestuario, Calcados e Beleza
- Transporte de Passageiros, Pet Shops, Supermercados

**Output estruturado:**
```python
{
    "is_compatible": bool,      # True = aprovado, False = rejeitado
    "category_label": str,      # Ex: "ENGENHARIA_E_INSTALACOES"
    "justification": str        # Explicacao em 1-2 frases
}
```

---

## Tecnologias Utilizadas

| Componente | Tecnologia |
|------------|------------|
| Framework Web | FastAPI |
| LLM | Google Gemini 2.0 Flash |
| LLM Framework | LangChain (langchain-google-genai) |
| API Externa | BrasilAPI (Receita Federal) |
| HTTP Client (async) | httpx |
| Validacao | Pydantic v2 |
| Rate Limiting | slowapi (20 req/min) |
| Retry | tenacity (3 tentativas) |

---

## Fluxo de Dados Completo

```
[Cliente HTTP]
     │
     │ POST /api/v1/companies/validate-cnpj
     │ Body: { "cnpj": "12.345.678/0001-90" }
     │
     ▼
[Sanitizacao]
     │ "12345678000190" (14 digitos)
     │
     ▼
[BrasilAPI]
     │ GET https://brasilapi.com.br/api/cnpj/v1/12345678000190
     │ Retorna: razao_social, situacao, cnaes...
     │
     ▼
[Check Situacao]
     │ descricao_situacao_cadastral == "ATIVA"?
     │
     ▼
[Agente de IA]
     │ Envia CNAEs ao Gemini
     │ Retorna: is_compatible, category_label, justification
     │
     ▼
[Resposta Final]
     │ { status: "VALID"/"INVALID", reason, ... }
     │
     ▼
[Cliente HTTP]
```

---

## Codigos de Erro

| Codigo | Quando ocorre |
|--------|---------------|
| `INVALID_CNPJ_FORMAT` | CNPJ nao tem 14 digitos apos limpeza |
| `CNPJ_NOT_FOUND` | BrasilAPI retornou 404 |
| `CNPJ_INACTIVE` | Situacao cadastral diferente de "ATIVA" |
| `INVALID_COMPANY_CATEGORY` | CNAEs incompativeis com setor solar/eletrico |

---

## Tratamento de Erros

- **CNPJ mal formatado** → resposta INVALID imediata (sem consulta externa)
- **BrasilAPI indisponivel** → HTTP 502 para o cliente
- **Falha na chamada LLM** → retry automatico (3 tentativas), se falhar → HTTP 500
- **Timeout BrasilAPI** → 15 segundos, apos isso → HTTP 502
