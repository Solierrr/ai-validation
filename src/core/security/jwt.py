"""Validação do JWT de usuário (RS256 via JWKS do api-auth)."""

import jwt as pyjwt
from ai_lib.security import decode_user_id as _decode_user_id
from jwt import PyJWKClient

from src.core.config.settings import get_settings


def decode_user_id(token: str) -> str | None:
    """Extrai o `sub` do JWT; None em qualquer falha, inclusive config ausente."""
    settings = get_settings()
    if not settings.JWT_JWKS_URL or not settings.JWT_ISSUER:
        return None
    return _decode_user_id(
        token, jwks_url=settings.JWT_JWKS_URL, issuer=settings.JWT_ISSUER
    )


_clients: dict[str, PyJWKClient] = {}


def _jwk_client(jwks_url: str) -> PyJWKClient:
    client = _clients.get(jwks_url)
    if client is None:
        client = _clients[jwks_url] = PyJWKClient(jwks_url)
    return client


def is_valid_access_token(token: str, *, jwks_url: str, issuer: str | None) -> bool:
    """Confere assinatura, emissor, `exp` e `sub`; rejeita tokens de outro `token_type`
    (por exemplo, refresh). Qualquer falha, inclusive JWKS fora do ar, devolve False."""
    try:
        signing_key = _jwk_client(jwks_url).get_signing_key_from_jwt(token)
        payload = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"require": ["exp", "sub"]},
        )
    except Exception:  # noqa: BLE001
        return False
    return payload.get("token_type", "access") == "access"
