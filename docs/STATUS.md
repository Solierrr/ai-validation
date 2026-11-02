<p align="center">
  <img src="../assets/readme/banners/fastapi.png" alt="FastAPI" width="100%">
</p>

# Situação

Levantamento da main `7855fc9f` em 2026-10-30.

- Há rotas de certificados, CNPJ, saúde e debug, com testes por domínio e exportação OpenAPI (2026-10-30).
- Não há `professional_routes` nem `/api/v1/professionals/validate` nesta main, e a rota esperada pelo cadastro central, protegida pela `X-Service-Key` do chamador, continua por implementar (2026-10-30).
- Os critérios numéricos de validade, carga horária e semelhança de nome são as regras de aceitação do produto (2026-10-30).
- O texto do bootstrap descreve validação pública, mas os routers exigem JWT, com `AUTH_REQUIRED` ativo por padrão, e o serviço está publicado no QA e na produção (2026-10-30).
- O Dockerfile usa Python sem versão fixa e as dependências majoritariamente não têm versão fixada. A biblioteca compartilhada agora vem de faixa no índice, contrariando o SHA antigo citado no checklist (2026-10-30).
- As imagens são baixadas por URLs HTTP ou HTTPS, com redirects, e a restrição ao Cloudinary, origem definida para os documentos, ainda não está no código (2026-10-30).
- Datas ausentes ou ilegíveis não causam reprovação independente na consolidação. Ela mantém a decisão do especialista. Nomes são comparados entre documentos, sem comparação com a identidade do JWT (2026-10-30).
- Algumas falhas de modelo e download são convertidas em reprovação de documento. Uma resposta 200 reprovada não comprova que o documento foi analisado com sucesso (2026-10-30).
- Debug guarda checkpoints em memória. O controle descarta execuções antigas e limita o conjunto, mas pode manter uma única execução acima do tamanho de referência. Não há banco persistente de execuções (2026-10-30).
- Readiness não confere modelos, JWKS ou BrasilAPI. O status do cluster não comprova uma validação funcional (2026-10-30).
