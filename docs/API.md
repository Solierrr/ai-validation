<p align="center">
  <img src="../assets/readme/banners/fastapi.png" alt="FastAPI" width="100%">
</p>

# Contrato HTTP

O contrato versionado fica em [openapi.yaml](https://github.com/Solierrr/ai-validation/blob/main/openapi.yaml), e o serviço oferece `/docs` e `/openapi.json` quando `DOCS_ENABLED` permite, por isso o contrato não é copiado para este documento.

## Autenticação

Os dois endpoints de validação exigem `Authorization` com Bearer JWT por padrão, e `AUTH_REQUIRED` pode desativar essa verificação. O resumo do bootstrap que chama as rotas de públicas está desatualizado em relação às dependências dos routers.

O health e o readiness são públicos, enquanto o debug é separado, exige o JWT de um administrador configurado e não aparece no OpenAPI. A rota de validação profissional, chamada pelo `api-core`, deve exigir a `X-Service-Key` do chamador, e ainda não existe nesta main.

## Grupos

| Operação | Finalidade | Limite por IP |
|---|---|---|
| `POST /api/v1/certificates/validate` | Dois certificados por URLs HTTP ou HTTPS | 10 por minuto |
| `POST /api/v1/companies/validate-cnpj` | Cadastro e atividades de empresa | 20 por minuto |
| `GET /health`, `GET /ready` | Processo e prontidão declarada | Não há decorador de limite nessas rotas |
| `POST /debug/certificates/validate`, `POST /debug/companies/validate-cnpj` | Etapas e execução administrativa | Controle por lista de administradores |

## Exemplo

O exemplo usa endereços reservados para documentação. Substituir por imagens sintéticas acessíveis do ambiente e fornecer o JWT sem gravá-lo no histórico.

```bash
curl --request POST http://localhost:8000/api/v1/certificates/validate   --header "Authorization: Bearer $ACCESS_TOKEN"   --header 'Content-Type: application/json'   --data '{"cert_nr10_url":"https://example.com/nr10.png","cert_nr35_url":"https://example.com/nr35.png"}'
```

Para empresas, enviar JSON com `cnpj` ao endpoint correspondente, usando dado sintético autorizado. Não enviar dados pessoais reais nos exemplos.

## Resultados e erros

Os certificados retornam `ACCEPT` ou `REJECTED` e as empresas retornam `VALID` ou `INVALID`, e uma reprovação ainda responde 200, com o motivo em `reason` e `error_code`. Alguns códigos de resultado são `ILLEGIBLE_DOCUMENT`, `NAME_MISMATCH`, `EXPIRED_CERTIFICATE`, `INSUFFICIENT_WORKLOAD`, `INVALID_CNPJ_FORMAT` e `CNPJ_INACTIVE`.

Falhas HTTP usam `application/problem+json` com `errorCode`, de acordo com o [contrato de erros](https://github.com/Solierrr/docs-warehouse/blob/main/docs/standards/ERRORS.md) e o [catálogo](https://github.com/Solierrr/docs-warehouse/blob/main/docs/standards/ERROR_CODES.md). Não confundir `error_code` do resultado com `errorCode` da falha HTTP.

Corpo inválido responde 422, autenticação inválida 401, limite 429 e falha inesperada 500. Sem configuração JWKS, a dependência responde 503. Falha na consulta cadastral responde 502. Alguns caminhos administrativos retornam JSON próprio com `detail` e `debug`, em vez de ProblemDetail.

As fontes são [certificados](https://github.com/Solierrr/ai-validation/blob/main/src/api/routes/certificate_routes.py), [empresas](https://github.com/Solierrr/ai-validation/blob/main/src/api/routes/cnpj_routes.py) e [debug](https://github.com/Solierrr/ai-validation/blob/main/src/api/routes/debug_routes.py).
