# Modo debug (`/debug/*`)

Roda um fluxo de validação e devolve, junto da resposta normal, as etapas que ele
percorreu: o que cada nó recebeu e devolveu e cada chamada de LLM feita dentro dele.
É para o playground do sandbox e para uso interno; não faz parte do contrato público e
não aparece no OpenAPI.

| Rota | Fluxo | Etapas que aparecem |
|---|---|---|
| `POST /debug/certificates/validate` | Certificados NR-10 e NR-35 (mesmo corpo de `/api/v1/certificates/validate`) | Os nós do grafo: `security_guardrail`, `nr10_agent`, `nr35_agent`, `consolidation` |
| `POST /debug/companies/validate-cnpj` | CNPJ (mesmo corpo de `/api/v1/companies/validate-cnpj`) | Uma única etapa, `cnpj_validation`, porque o CNPJ não é um grafo; a consulta à BrasilAPI e a chamada do agente de IA ficam dentro dela |

## Segurança

As rotas respondem `404` quando qualquer condição abaixo falha, sem revelar que existem:

- `DEBUG_ADMIN_SUBS` tem ao menos um UUID válido. Não há outra flag: o modo está sempre
  ativo, e esvaziar a lista é o que o desliga.
- `ENVIRONMENT` é `LOCAL`, `DEV`, `QA` ou `PROD` (sem diferenciar maiúsculas). É uma
  lista de permitidos: um valor desconhecido (`PRD`, `staging`, vazio) bloqueia, mesmo
  com admins configurados. O padrão é `LOCAL`, então defina a variável em QA e PROD.

Em PROD o modo funciona como nos outros ambientes, e quem controla o acesso é
`DEBUG_ADMIN_SUBS`. A execução usa os LLMs e a BrasilAPI reais: gasta cota e custo reais.

Depois disso, o JWT é validado (RS256 pelo JWKS do api-auth):

| Situação | Status |
|---|---|
| Sem `Authorization: Bearer` ou token inválido (inclusive sem `JWT_JWKS_URL`/`JWT_ISSUER` configurados) | `401` |
| `sub` fora de `DEBUG_ADMIN_SUBS` | `403` |

Cada execução autorizada deixa uma linha de log com o `sub` e o ambiente
(`Execução de debug (sub=..., ambiente=...)`).

`DEBUG_ADMIN_SUBS` é uma lista de UUIDs separados por vírgula. Entradas que não são
UUID são ignoradas; lista vazia (ou só com entradas inválidas) fecha as rotas com 404.

## Resposta

Os campos normais da rota equivalente mais `debug`:

```json
{
  "status": "ACCEPT",
  "reason": "...",
  "error_code": null,
  "extracted_data": {},
  "debug": {
    "environment": "QA",
    "persisted": false,
    "duration_ms": 5210.4,
    "nodes": [
      {
        "order": 1,
        "node": "security_guardrail",
        "started_at": "2026-10-23T12:00:00+00:00",
        "duration_ms": 2100.7,
        "status": "ok",
        "input": { "cert_nr10_url": "https://.../nr10.jpg?[omitido]", "current_date": "2026-10-23" },
        "output": { "is_safe": true, "cert_nr10_b64": "[imagem omitida]" },
        "llm_calls": [
          { "model": "gemini-2.5-flash", "prompt": [{ "type": "system", "content": "..." }],
            "completion": "[{\"is_safe\": true}]", "tokens_in": 1200, "tokens_out": 8,
            "latency_ms": 1980.3, "error": null }
        ],
        "error": null
      }
    ],
    "llm_calls_outside_nodes": [],
    "truncated": false
  }
}
```

- `nodes` segue a ordem de execução.
- O LLM com saída estruturada responde por tool call; nesse caso `completion` traz os
  argumentos da chamada em JSON.
- `tokens_*` e `model` podem vir `null` quando o provedor não informa.
- Se a execução falha, a rota devolve o status do erro (`500`, ou `502` quando a
  BrasilAPI falha no CNPJ) com `{ "detail": "...", "debug": {...} }`, e o `debug` traz o
  que foi coletado até ali.

## O que nunca sai

- **Imagens:** o conteúdo em base64 (campos `cert_*_b64`, partes `image_url` dos prompts e
  qualquer `data:...;base64,`) vira `[imagem omitida]`.
- **URLs assinadas:** a query string (`?X-Signature=...`) é trocada por `?[omitido]`;
  o resto da URL fica.
- **PII:** CPF, CNPJ, telefone e e-mail viram `[CPF]`, `[CNPJ]`, `[TELEFONE]` e `[EMAIL]`
  em todo o bloco `debug`. Nome e endereço não são mascarados: use dados de teste.
- **Tamanho:** os prompts saem inteiros, sem limite. Os demais textos (entrada e saída
  dos nós, resposta do LLM) são cortados em 4.000 caracteres; quando algo é cortado,
  `truncated` é `true`.

Nada é gravado em banco. Só as execuções de certificados ficam em memória por alguns
minutos, para a reexecução de um nó (próxima seção).

## Reexecutar um nó com prompts editados

Cada chamada de LLM em `debug.nodes[].llm_calls[]` traz o prompt completo em `prompt`
(lista de `{type, content, editable}`) e `prompt_complete`. Só as mensagens com
`editable: true` podem ser trocadas, e só se `prompt_complete` for `true` (nada foi
mascarado). Mensagens `system` são editáveis; no CNPJ, o prompt é uma única
mensagem `human` (modelo de instruções com os dados da BrasilAPI) e também é editável.
A parte `image_url` do prompt nunca é editável e nunca sai.

### Certificados

`POST /debug/certificates/validate` devolve `debug.run_id` e `debug.turn` (sempre `0`).
Para reexecutar um nó, envie o mesmo corpo mais `custom`:

```json
{
  "cert_nr10_url": "https://.../nr10.jpg",
  "cert_nr35_url": "https://.../nr35.png",
  "custom": {
    "run_id": "<debug.run_id>",
    "node": "nr10_agent",
    "occurrence": 0,
    "stop_after_node": true,
    "prompts": [
      { "call": 0, "prompt": [{ "type": "system", "content": "novo prompt" }, { "type": "human", "content": "[imagem omitida]" }] }
    ]
  }
}
```

A rota restaura o estado que o nó recebeu na execução original (as imagens ficam no
estado, então nada é baixado de novo), roda só esse nó com o prompt editado e para nele.
A resposta traz `status`, `reason`, `error_code` e `extracted_data` como `null` e:

```json
{ "debug": { "nodes": [ { "node": "nr10_agent", "...": "..." } ],
             "custom": { "run_id": "...", "node": "nr10_agent", "turn": 0, "occurrence": 0,
                         "stopped": true, "overrides_applied": 1, "next": ["nr35_agent"] } } }
```

`overrides_applied` é quantas mensagens foram trocadas de fato. O `next` diz qual nó viria
depois. Se o nó faz nova chamada ao LLM (rate limit e fallback de provedor), a edição vale
para todas as chamadas dele.

| Status | Quando |
|---|---|
| `404` | Execução expirada, de outro admin, reiniciada ou em outra instância; nó ou ocorrência inexistente |
| `422` | Corpo inválido (`run_id` que não é UUID, `node` fora do padrão, `stop_after_node` diferente de `true`) ou nó que não pode ser reexecutado |
| `500` | Falha no nó, com o `debug` parcial |

As execuções ficam na memória da instância: no máximo 5 (as mais antigas saem primeiro),
por 30 minutos, dentro de 64 MB de imagens. Com mais de uma réplica, a reexecução pode cair
em uma instância que não tem a execução e responder `404`; mantenha o debug em uma só
instância ou use afinidade de sessão. Cada reexecução deixa uma linha de log com o `sub`,
o nó e a quantidade de prompts, sem o conteúdo.

### CNPJ

O CNPJ é um nó só (`cnpj_validation`): reexecutar é rodar o fluxo inteiro de novo com o
prompt editado, então envie o CNPJ de novo com `custom`:

```json
{ "cnpj": "12.345.678/0001-90",
  "custom": { "node": "cnpj_validation", "stop_after_node": true,
              "prompts": [{ "call": 0, "prompt": [{ "type": "human", "content": "novo prompt" }] }] } }
```

A BrasilAPI é consultada de novo, então os dados da empresa podem ter mudado desde a
execução original. A resposta traz o resultado normal e `debug.custom` com
`next: []`. Como o fluxo inclui só a consulta e a análise do LLM, não há efeito fora do serviço.

## Variáveis

| Variável | Padrão | Uso |
|---|---|---|
| `ENVIRONMENT` | `LOCAL` | Ambiente; defina em QA e PROD |
| `DEBUG_ADMIN_SUBS` | vazio | UUIDs (`sub` do JWT) autorizados, separados por vírgula; vazio desliga o modo |
| `JWT_JWKS_URL` | vazio | JWKS do api-auth, para validar o JWT |
| `JWT_ISSUER` | vazio | Issuer esperado (`solaria-auth`) |

Exemplo:

```bash
curl -X POST "$URL/debug/companies/validate-cnpj" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"cnpj":"12.345.678/0001-90"}'
```
