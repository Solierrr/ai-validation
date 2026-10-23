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
- **Tamanho:** cada texto é cortado em 4.000 caracteres e o bloco `debug` tem teto de
  256 KB (os limites por campo diminuem até caber). Quando algo é cortado, `truncated` é
  `true`. Se mesmo assim passar do teto, as entradas e os prompts são omitidos.

O debug existe só na resposta: nada é gravado.

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
