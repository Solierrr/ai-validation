# Fluxo do Agente — AI Certificate Validator

## Arquitetura Geral

O sistema utiliza uma **pipeline multi-agente** orquestrada pelo [LangGraph](https://github.com/langchain-ai/langgraph). Cada nó do grafo é um agente especializado que processa parte da validacao.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         API FastAPI                                 │
│                POST /api/v1/certificates/validate                   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      LangGraph Pipeline                              │
│                                                                      │
│   ┌──────────────────────┐                                           │
│   │  Security Guardrail  │ ← Detecta prompt injection e docs         │
│   │    (LLM Vision)      │   ilegíveis                               │
│   └──────────┬───────────┘                                           │
│              │                                                       │
│         is_safe?                                                     │
│        /        \                                                    │
│      YES         NO                                                  │
│       │           │                                                  │
│       ▼           │                                                  │
│   ┌──────────┐    │                                                  │
│   │ NR-10    │    │                                                  │
│   │ Agent    │    │ ← Valida certificado NR-10                       │
│   │(LLM Vis.)│    │                                                  │
│   └───┬──────┘    │                                                  │
│       │           │                                                  │
│       ▼           │                                                  │
│   ┌──────────┐    │                                                  │
│   │ NR-35    │    │                                                  │
│   │ Agent    │    │ ← Valida certificado NR-35                       │
│   │(LLM Vis.)│    │                                                  │
│   └────┬─────┘    │                                                  │
│        │          │                                                  │
│        ▼          ▼                                                  │
│   ┌─────────────────────┐                                            │
│   │   Consolidation     │ ← Logica determinística (sem LLM)          │
│   │   (Deterministic)   │   Fuzzy name match + regras de negocio     │
│   └──────────┬──────────┘                                            │
│              │                                                       │
└──────────────┼───────────────────────────────────────────────────────┘
               │
               ▼
        Resposta Final
      (ACCEPT / REJECTED)
```

---

## Estado Global (CertificateGraphState)

Todos os nós compartilham um estado tipado (`TypedDict`):

```python
class CertificateGraphState(TypedDict):
    # Inputs da API
    cert_nr10_url: str          # URL da imagem NR-10
    cert_nr35_url: str          # URL da imagem NR-35
    current_date: str           # Data atual (YYYY-MM-DD)

    # Controle de seguranca
    is_safe: bool
    security_error_code: Optional[str]
    security_reason: Optional[str]

    # Resultados dos agentes
    nr10_result: Optional[Dict[str, Any]]
    nr35_result: Optional[Dict[str, Any]]

    # Decisao final
    status: str                 # "ACCEPT" ou "REJECTED"
    reason: str
    error_code: Optional[str]
    extracted_data: Optional[Dict[str, Any]]
```

---

## Detalhamento dos Nós

### 1. Security Guardrail

**Arquivo:** `src/workflow/nodes/security_guardrail_node.py`  
**Tipo:** LLM Vision (Gemini)  
**Objetivo:** Primeira linha de defesa antes dos agentes especialistas.

**O que verifica:**
- Prompt injection (instrucoes ocultas direcionadas a IA)
- Documentos ilegíveis (imagem em branco, selfie, objeto aleatorio)
- Edicoes digitais tentando sobrescrever instrucoes do sistema

**Processo:**
1. Faz download das duas imagens (NR-10 e NR-35)
2. Envia ambas ao LLM Vision com prompt de seguranca
3. Retorna `is_safe: true/false` para o estado

**Output:**
```python
{
    "is_safe": bool,
    "security_error_code": str | None,
    "security_reason": str | None
}
```

**Roteamento condicional:**
- `is_safe = true` → segue para NR-10 Agent
- `is_safe = false` → pula direto para Consolidation (rejeicao imediata)

---

### 2. NR-10 Agent

**Arquivo:** `src/workflow/nodes/nr10_agent_node.py`  
**Tipo:** LLM Vision (Gemini) com Structured Output  
**Objetivo:** Validar o certificado NR-10 (Seguranca em Instalacoes Eletricas).

**Criterios de validacao:**

| Criterio | Regra |
|----------|-------|
| Estrutura minima | 6 elementos obrigatorios (cabecalho, nome, instituicao, carga horaria, data, assinatura) |
| Conteudo | Deve ser explicitamente sobre NR-10 |
| Validade | Emitido ha no maximo 24 meses |
| Carga horaria | Minimo 20h (reciclagem) ou 40h (formacao) |

**Processo:**
1. Faz download da imagem do certificado NR-10
2. Codifica em base64
3. Envia ao Gemini Vision com prompt estruturado
4. Recebe output estruturado (Pydantic model)

**Output:**
```python
{
    "nr10_result": {
        "valid": bool,
        "error_code": str | None,
        "error_reason": str | None,
        "student_name": str | None,
        "institution_name": str | None,
        "workload_hours": int | None,
        "issue_date": str | None,       # YYYY-MM-DD
        "has_required_structure": bool
    }
}
```

---

### 3. NR-35 Agent

**Arquivo:** `src/workflow/nodes/nr35_agent_node.py`  
**Tipo:** LLM Vision (Gemini) com Structured Output  
**Objetivo:** Validar o certificado NR-35 (Trabalho em Altura).

**Criterios de validacao:**

| Criterio | Regra |
|----------|-------|
| Estrutura minima | 6 elementos obrigatorios (mesmos do NR-10) |
| Conteudo | Deve ser explicitamente sobre NR-35 ou Trabalho em Altura |
| Validade | Emitido ha no maximo 24 meses |
| Carga horaria | Minimo 8h |

**Processo:** Identico ao NR-10 Agent, com regras especificas de NR-35.

**Output:**
```python
{
    "nr35_result": {
        "valid": bool,
        "error_code": str | None,
        "error_reason": str | None,
        "student_name": str | None,
        "institution_name": str | None,
        "workload_hours": int | None,
        "issue_date": str | None,       # YYYY-MM-DD
        "has_required_structure": bool
    }
}
```

---

### 4. Consolidation (Deterministic)

**Arquivo:** `src/workflow/nodes/consolidation_node.py`  
**Tipo:** Logica deterministica (SEM LLM)  
**Objetivo:** Tomar a decisao final com base nos resultados dos agentes.

**Pipeline de verificacao (em ordem):**

```
1. Security check  → se is_safe=false → REJECTED
2. NR-10 valido?   → se valid=false   → REJECTED
3. NR-10 workload  → se < 20h         → REJECTED
4. NR-35 valido?   → se valid=false   → REJECTED
5. NR-35 workload  → se < 8h          → REJECTED
6. Nome extraido?  → se vazio         → REJECTED
7. Fuzzy match     → se score < 85%   → REJECTED (NAME_MISMATCH)
8. Tudo OK                            → ACCEPT
```

**Fuzzy Name Matching:**
- Utiliza `rapidfuzz.fuzz.token_set_ratio`
- Threshold de similaridade: **85%**
- Compara o nome do aluno extraido do NR-10 com o do NR-35
- Garante que ambos certificados pertencem ao mesmo profissional

---

## Tecnologias Utilizadas

| Componente | Tecnologia |
|------------|------------|
| Framework Web | FastAPI |
| Orquestracao | LangGraph (StateGraph) |
| LLM | Google Gemini 2.0 Flash (Vision) |
| LLM Framework | LangChain (langchain-google-genai) |
| Validacao | Pydantic v2 |
| Fuzzy Matching | RapidFuzz |
| HTTP Client | httpx |
| Configuracao | pydantic-settings + .env |

---

## Fluxo de Dados Completo

```
[Cliente HTTP]
     │
     │ POST /api/v1/certificates/validate
     │ Body: { cert_nr10_url, cert_nr35_url }
     │
     ▼
[FastAPI Route Handler]
     │
     │ Injeta current_date = date.today()
     │ Monta initial_state
     │
     ▼
[compiled_graph.ainvoke(initial_state)]
     │
     ├─► [Security Guardrail]
     │       │ Download ambas imagens
     │       │ Gemini Vision → detecta riscos
     │       │ Retorna: is_safe, security_error_code, security_reason
     │       │
     │       ├─ is_safe=true ──► [NR-10 Agent]
     │       │                       │ Download imagem NR-10
     │       │                       │ Gemini Vision → extrai dados
     │       │                       │ Retorna: nr10_result
     │       │                       │
     │       │                       ▼
     │       │                   [NR-35 Agent]
     │       │                       │ Download imagem NR-35
     │       │                       │ Gemini Vision → extrai dados
     │       │                       │ Retorna: nr35_result
     │       │                       │
     │       │                       ▼
     │       │                   [Consolidation]
     │       │                       │ Verifica validade
     │       │                       │ Verifica carga horaria
     │       │                       │ Fuzzy name match
     │       │                       │ Retorna: status, reason, error_code
     │       │
     │       └─ is_safe=false ─► [Consolidation]
     │                               │ Rejeicao imediata por seguranca
     │
     ▼
[FastAPI Response]
     │ { status, reason, error_code, extracted_data }
     │
     ▼
[Cliente HTTP]
```

---

## Tratamento de Erros

Cada nó possui tratamento de excecoes proprio:

- **Falha no download de imagem** → retorna `error_code: "ILLEGIBLE_DOCUMENT"`
- **Falha na chamada LLM** → retorna resultado com `valid: false` e erro descritivo
- **Excecao nao tratada na pipeline** → FastAPI retorna HTTP 500 com mensagem generica

O sistema e **fail-safe**: qualquer falha resulta em `REJECTED`, nunca em falso positivo.
