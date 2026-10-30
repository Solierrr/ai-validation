from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

GENERIC_BY_STATUS = {
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_FAILED",
    429: "RATE_LIMITED",
    502: "DEPENDENCY_UNAVAILABLE",
    503: "DEPENDENCY_UNAVAILABLE",
}


class ApiError(Exception):
    def __init__(self, status: int, error_code: str, detail: str, **extra):
        self.status = status
        self.error_code = error_code
        self.detail = detail
        self.extra = extra


def problem(
    request: Request, status: int, error_code: str, detail: str, **extra
) -> JSONResponse:
    body = {
        "type": "about:blank",
        "title": error_code,
        "status": status,
        "errorCode": error_code,
        "detail": detail,
        "instance": request.url.path,
        "timestamp": datetime.now(UTC).isoformat(),
        **extra,
    }
    return JSONResponse(body, status_code=status, media_type="application/problem+json")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return problem(request, exc.status, exc.error_code, exc.detail, **exc.extra)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code = GENERIC_BY_STATUS.get(exc.status_code, "INTERNAL_ERROR")
        response = problem(request, exc.status_code, code, str(exc.detail))
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        errors = [
            {
                "field": ".".join(str(p) for p in e["loc"][1:]),
                "errorCode": "VALIDATION_FAILED",
                "detail": e["msg"],
            }
            for e in exc.errors()
        ]
        return problem(
            request,
            422,
            "VALIDATION_FAILED",
            "Erro de validação nos campos da requisição.",
            errors=errors,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        return problem(
            request, 500, "INTERNAL_ERROR", "Ocorreu um erro interno inesperado."
        )
