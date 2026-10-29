"""Dependência que exige o access token do api-auth nas rotas de validação."""

import asyncio

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.config.settings import get_settings
from src.core.security.jwt import is_valid_access_token

bearer_scheme = HTTPBearer(
    auto_error=False,
    bearerFormat="JWT",
    description="Access token JWT emitido pelo api-auth.",
)


async def require_access_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> None:
    settings = get_settings()
    if not settings.AUTH_REQUIRED:
        return
    if not settings.JWT_JWKS_URL:
        raise HTTPException(
            status_code=503, detail="Validação do access token não configurada"
        )
    if credentials is None or not await asyncio.to_thread(
        is_valid_access_token,
        credentials.credentials,
        jwks_url=settings.JWT_JWKS_URL,
        issuer=settings.JWT_ISSUER,
    ):
        raise HTTPException(
            status_code=401,
            detail="Access token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
