"""Validação do access token emitido pelo api-auth (RS256, chaves públicas via JWKS)."""

import jwt as pyjwt
from jwt import PyJWKClient

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
