import hmac

from fastapi import Security
from fastapi.security import APIKeyHeader

from src.api.errors import ApiError
from src.core.config.settings import get_settings

service_key_header = APIKeyHeader(
    name="X-Service-Key", scheme_name="serviceKey", auto_error=False
)


def require_caller(*callers: str):
    def dependency(key: str | None = Security(service_key_header)) -> str:
        if key:
            for caller, expected in get_settings().service_keys.items():
                if expected and hmac.compare_digest(key.encode(), expected.encode()):
                    if caller in callers:
                        return caller
                    raise ApiError(
                        403, "FORBIDDEN", "Serviço chamador não autorizado nesta rota."
                    )
        raise ApiError(401, "UNAUTHENTICATED", "Chave de serviço ausente ou inválida.")

    return dependency
