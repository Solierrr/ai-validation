<p align="center">
  <img src="../assets/readme/banners/fastapi.png" alt="FastAPI" width="100%">
</p>

# Depuração administrativa

Um administrador consulta etapas ou reexecuta um nó sobre estado disponível na instância, sem alterar o fluxo público.

```mermaid
sequenceDiagram
  participant A as Administrador
  participant H as Rota de debug
  participant M as Estado em memória
  participant G as Grafo ou análise
  A->>H: HTTP e JWT administrativo
  H->>H: Conferir ambiente e lista de administradores
  alt Sem autorização
    H-->>A: 404, 401 ou 403
  else Execução nova
    H->>G: Executar e coletar etapas
    G-->>M: Checkpoints de certificado
    H-->>A: Resultado e debug
  else Replay de certificado
    H->>M: Buscar execução do mesmo administrador
    alt Expirou ou outra instância
      H-->>A: 404
    else Estado disponível
      H->>G: Executar apenas nó solicitado
      H-->>A: Etapas e próximos nós
    end
  end
```

## Falhas e limites

O controle usa referência de cinco execuções, 30 minutos e 64 MiB estimados no conjunto, com descarte sob consulta ou inclusão. Não é retenção durável nem limite rígido para uma execução isolada. Replay de certificado aplica overrides de sistema e para após o nó. Empresa pode ter nova análise com prompts personalizados. Algumas falhas usam JSON próprio.

Fonte em [implementação](https://github.com/Solierrr/ai-validation/blob/main/src/api/routes/debug_routes.py). O contexto entre serviços está no [mapa de integrações](https://github.com/Solierrr/docs-warehouse/blob/main/docs/flows/INTEGRATIONS.md).
