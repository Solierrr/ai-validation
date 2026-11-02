<p align="center">
  <img src="../assets/readme/banners/fastapi.png" alt="FastAPI" width="100%">
</p>

# Validação de certificados

A solicitação envia duas URLs e recebe a decisão consolidada, sem gravar aprovação no cadastro central.

```mermaid
flowchart TD
  A[Validar JWT e corpo] --> B[Aplicar limite por IP]
  B --> C[Baixar duas imagens]
  C --> D[Análise de segurança]
  C -->|Falha de download| R[Reprovar documento]
  D -->|Inseguro ou falha tratada| R
  D -->|Seguro| E[Extrair certificado de instalações]
  E --> F[Extrair certificado de altura]
  F --> G[Consolidar regras e nomes]
  G -->|Critério reprovado| R
  G -->|Critérios aceitos| H[Retornar ACCEPT]
  R --> I[Retornar REJECTED]
  B -->|Limite excedido| J[Responder 429]
```

## Falhas e limites

JWT inválido e corpo inválido impedem o fluxo. Download ou falha capturada de análise pode produzir reprovação em 200. Exceção não tratada do grafo responde 500. A consolidação usa 730 dias, cargas mínimas e similaridade, sem nova chamada a modelo.

Fonte em [implementação](https://github.com/Solierrr/ai-validation/blob/main/src/workflow/nodes/consolidation_node.py). O contexto entre serviços está no [mapa de integrações](https://github.com/Solierrr/docs-warehouse/blob/main/docs/flows/INTEGRATIONS.md).
