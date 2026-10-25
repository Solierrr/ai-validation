# API Documentation — AI Validation Platform

## Visao Geral

Plataforma de validacao automatizada com IA, composta por dois fluxos:
1. **Certificados NR-10/NR-35** — pipeline multi-agente com LLM Vision.
2. **CNPJ de Empresas** — validacao de compatibilidade de atividades econômicas.

**Base URL:** `http://localhost:8000`  
**Versao:** a do release, lida do `version.txt`

O contrato completo e gerado do codigo: `GET /openapi.json` (Swagger em `/docs`, desligados com `DOCS_ENABLED=false`) e `openapi.yaml` na raiz, exportado por `make openapi`.

---

## Endpoints

### `GET /health`

Indica se o processo esta vivo. Rota publica.

**Tags:** `Saúde`

**Resposta 200:**
```json
{
  "status": "UP",
  "version": "3.1.0"
}
```

### `GET /ready`

Indica se o servico esta pronto para atender. O servico nao tem banco nem cache; os provedores de LLM (com fallback) e a BrasilAPI ficam fora do pronto. Rota publica.

**Tags:** `Saúde`

**Resposta 200:**
```json
{
  "status": "UP"
}
```

---

## Erros HTTP

Todo erro HTTP responde `application/problem+json` no contrato de erro da organizacao. Documento ou CNPJ reprovado nao e erro: volta 200 com `status` `REJECTED` ou `INVALID` e o `error_code` da tabela de cada fluxo.

| Status | `errorCode` | Quando |
|--------|-------------|--------|
| 422 | `VALIDATION_FAILED` | corpo invalido (detalhes em `errors`) |
| 429 | `RATE_LIMITED` | limite de requisicoes por IP atingido |
| 500 | `INTERNAL_ERROR` | falha inesperada na pipeline ou no agente |
| 502 | `DEPENDENCY_UNAVAILABLE` | falha na consulta a BrasilAPI |

```json
{
  "type": "about:blank",
  "title": "DEPENDENCY_UNAVAILABLE",
  "status": 502,
  "errorCode": "DEPENDENCY_UNAVAILABLE",
  "detail": "Erro ao consultar dados do CNPJ na Receita Federal.",
  "instance": "/api/v1/companies/validate-cnpj",
  "timestamp": "2026-10-25T13:45:00+00:00"
}
```

---

## Fluxo 1: Validacao de Certificados

### `POST /api/v1/certificates/validate`

Valida certificados NR-10 e NR-35 atraves da pipeline multi-agente com LLM Vision.

**Tags:** `Certificados`  
**Rate Limit:** 10 requests/minuto por IP

#### Request Body

| Campo | Tipo | Obrigatorio | Descricao |
|-------|------|-------------|-----------|
| `cert_nr10_url` | `string (URL)` | Sim | URL da imagem do certificado NR-10 |
| `cert_nr35_url` | `string (URL)` | Sim | URL da imagem do certificado NR-35 |

**Exemplo de Request:**
```json
{
  "cert_nr10_url": "https://storage.meuapp.com/docs/nr10_document.jpg",
  "cert_nr35_url": "https://storage.meuapp.com/docs/nr35_document.png"
}
```

#### Response (200 OK)

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `status` | `string` | `"ACCEPT"` ou `"REJECTED"` |
| `reason` | `string` | Explicacao do resultado |
| `error_code` | `string \| null` | Codigo de erro padronizado (quando rejeitado) |
| `extracted_data` | `object \| null` | Dados extraidos dos certificados (quando aceito) |

**Exemplo — Aprovado:**
```json
{
  "status": "ACCEPT",
  "reason": "Ambos os certificados possuem estrutura valida, carga horaria adequada, estao no prazo de validade (24 meses) e pertencem ao mesmo profissional.",
  "error_code": null,
  "extracted_data": {
    "detected_student_name": "Joao da Silva",
    "nr10": {
      "valid": true,
      "institution_name": "SENAI",
      "workload_hours": 40,
      "issue_date": "2025-03-15",
      "has_required_structure": true
    },
    "nr35": {
      "valid": true,
      "institution_name": "SENAI",
      "workload_hours": 8,
      "issue_date": "2025-04-10",
      "has_required_structure": true
    }
  }
}
```

**Exemplo — Rejeitado:**
```json
{
  "status": "REJECTED",
  "reason": "Falha na NR-10: Certificado expirado (emitido ha mais de 24 meses).",
  "error_code": "EXPIRED_CERTIFICATE",
  "extracted_data": null
}
```

#### Codigos de Erro (Certificados)

| Codigo | Descricao |
|--------|-----------|
| `SECURITY_RISK` | Risco de seguranca detectado (prompt injection, documento ilegivel) |
| `ILLEGIBLE_DOCUMENT` | Imagem nao pode ser baixada ou processada |
| `INVALID_NR10` | Certificado NR-10 invalido (estrutura, conteudo) |
| `INVALID_NR35` | Certificado NR-35 invalido (estrutura, conteudo) |
| `INSUFFICIENT_WORKLOAD` | Carga horaria abaixo do minimo (NR-10: 20h, NR-35: 8h) |
| `EXPIRED_CERTIFICATE` | Certificado com mais de 24 meses de emissao |
| `MISSING_STRUCTURE` | Certificado sem estrutura minima obrigatoria |
| `MISSING_STUDENT_NAME` | Nome do aluno nao extraido de um ou ambos certificados |
| `NAME_MISMATCH` | Nomes nos certificados NR-10 e NR-35 nao correspondem |

---

## Fluxo 2: Validacao de CNPJ

### `POST /api/v1/companies/validate-cnpj`

Valida se uma empresa parceira possui atividades economicas compativeis com o setor solar/eletrico.

**Tags:** `Empresas`  
**Rate Limit:** 20 requests/minuto por IP

#### Request Body

| Campo | Tipo | Obrigatorio | Descricao |
|-------|------|-------------|-----------|
| `cnpj` | `string` | Sim | CNPJ com ou sem formatacao (pontos, tracos, barras) |

**Exemplo de Request:**
```json
{
  "cnpj": "12.345.678/0001-90"
}
```

#### Response (200 OK)

| Campo | Tipo | Descricao |
|-------|------|-----------|
| `status` | `string` | `"VALID"` ou `"INVALID"` |
| `cnpj` | `string` | CNPJ sanitizado (apenas 14 digitos) |
| `company_name` | `string \| null` | Razao social oficial |
| `trade_name` | `string \| null` | Nome fantasia |
| `is_active` | `boolean` | Se o CNPJ esta ativo na Receita Federal |
| `matched_category` | `string \| null` | Categoria compativel identificada (quando VALID) |
| `error_code` | `string \| null` | Codigo de erro (quando INVALID) |
| `reason` | `string` | Detalhamento amigavel para exibicao no app |

**Exemplo — Aprovado (VALID):**
```json
{
  "status": "VALID",
  "cnpj": "12345678000190",
  "company_name": "SOLAR ENERGY ENGENHARIA E INSTALACOES LTDA",
  "trade_name": "SOLAR ENERGY",
  "is_active": true,
  "matched_category": "ENGENHARIA_E_INSTALACOES_ELETRICAS",
  "error_code": null,
  "reason": "Empresa ativa e com ramo de atividade plenamente compativel com o setor solar e eletrico."
}
```

**Exemplo — Rejeitado por categoria (INVALID):**
```json
{
  "status": "INVALID",
  "cnpj": "98765432000110",
  "company_name": "DROGARIA E FARMACIA CENTRAL LTDA",
  "trade_name": "FARMACIA CENTRAL",
  "is_active": true,
  "matched_category": null,
  "error_code": "INVALID_COMPANY_CATEGORY",
  "reason": "A empresa esta ativa, mas seu ramo de atividade nao possui vinculo com energia solar, engenharia ou instalacoes eletricas."
}
```

**Exemplo — Rejeitado por CNPJ inativo (INVALID):**
```json
{
  "status": "INVALID",
  "cnpj": "11222333000199",
  "company_name": null,
  "trade_name": null,
  "is_active": false,
  "matched_category": null,
  "error_code": "CNPJ_INACTIVE",
  "reason": "O CNPJ informado nao esta ativo na Receita Federal (Situacao: BAIXADA)."
}
```

#### Codigos de Erro (CNPJ)

| Codigo | Descricao |
|--------|-----------|
| `INVALID_CNPJ_FORMAT` | CNPJ nao possui 14 digitos validos apos limpeza |
| `CNPJ_NOT_FOUND` | CNPJ nao localizado na base da Receita Federal |
| `CNPJ_INACTIVE` | CNPJ existe, mas situacao cadastral nao e "ATIVA" |
| `INVALID_COMPANY_CATEGORY` | CNPJ ativo, mas CNAEs sem relacao com setor solar/eletrico |

#### Response (502 Bad Gateway)

Retornado quando a consulta a BrasilAPI falha, com `errorCode` `DEPENDENCY_UNAVAILABLE` (ver [Erros HTTP](#erros-http)).

---

## Configuracao

Variaveis de ambiente (`.env`):

| Variavel | Obrigatoria | Default | Descricao |
|----------|-------------|---------|-----------|
| `GEMINI_API_KEY` | Sim | — | Chave da API do Google Gemini |
| `LLM_MODEL` | Nao | `gemini-2.0-flash` | Modelo LLM a ser utilizado |
| `LLM_TEMPERATURE` | Nao | `0.0` | Temperatura do modelo (0 = deterministico) |
| `DOCS_ENABLED` | Nao | `true` | Liga o Swagger (`/docs`) e o contrato (`/openapi.json`); `false` em PROD |
| `SERVICE_KEY_API_CORE` | Nao | vazio | Chave de servico do `api-core` (cabecalho `X-Service-Key`, minimo de 32 caracteres); vazia recusa o chamador |

---

## Como Executar

```bash
# Instalar dependencias
pip install -r requirements.txt

# Configurar variaveis de ambiente
cp .env.example .env
# Editar .env com sua GEMINI_API_KEY

# Iniciar o servidor
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

A documentacao interativa (Swagger) fica disponivel em: `http://localhost:8000/docs`
