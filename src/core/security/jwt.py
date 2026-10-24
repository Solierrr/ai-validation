"""Validação do JWT de usuário (RS256 via JWKS do api-auth)."""

from ai_lib.security import decode_user_id as _decode_user_id

from src.core.config.settings import get_settings


def decode_user_id(token: str) -> str | None:
    """Extrai o `sub` do JWT; None em qualquer falha, inclusive config ausente."""
    settings = get_settings()
    if not settings.JWT_JWKS_URL or not settings.JWT_ISSUER:
        return None
    return _decode_user_id(
        token, jwks_url=settings.JWT_JWKS_URL, issuer=settings.JWT_ISSUER
    )
