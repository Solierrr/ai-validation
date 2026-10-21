import hmac
import logging
import os

from fastapi import APIRouter, Depends, Header, HTTPException

from src.api.schemas.professional_schemas import (
    ProfessionalValidationRequest,
    ProfessionalValidationResponse,
)
from src.services.professional_validation import validate_professional

router = APIRouter(prefix="/api/v1", tags=["professionals"])
logger = logging.getLogger(__name__)


def require_service_token(authorization: str = Header(default="")):
    expected = os.environ.get("VALIDATION_SERVICE_TOKEN", "")
    if len(expected) < 32:
        raise HTTPException(503, "Service authentication is not configured")
    if not hmac.compare_digest(authorization.encode(), f"Bearer {expected}".encode()):
        raise HTTPException(401, "Invalid service authentication")


@router.post(
    "/professionals/validate",
    response_model=ProfessionalValidationResponse,
    dependencies=[Depends(require_service_token)],
)
def validate(payload: ProfessionalValidationRequest):
    try:
        return validate_professional(payload)
    except HTTPException:
        raise
    except Exception as exception:
        logger.error(
            "Professional validation failed",
            extra={"submission_id": str(payload.submissionId)},
        )
        raise HTTPException(503, "Validation is temporarily unavailable") from exception
