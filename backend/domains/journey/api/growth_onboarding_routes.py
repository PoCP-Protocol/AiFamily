"""HTTP boundary for ``StartGrowthOnboarding``.

The route only translates trusted request context into a command.  It never
constructs an adapter, writes a table, or short-circuits the transaction
boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from ..application.growth_onboarding import (
    GrowthOnboardingApplication,
    StartGrowthOnboardingCommand,
)
from ..domain.errors import (
    JourneyConflictError,
    JourneyForbiddenError,
    JourneyNotFoundError,
    JourneyValidationError,
)

router = APIRouter()


@dataclass(frozen=True)
class GrowthOnboardingActorContext:
    """Trusted actor and tenant scope resolved by the composition root."""

    tenant_id: str
    family_id: str
    actor_id: str
    actor_type: str = "HUMAN"


class StartGrowthOnboardingRequest(BaseModel):
    intent_id: str = Field(min_length=1, max_length=128)


async def get_growth_onboarding_application() -> GrowthOnboardingApplication:
    """Fail closed until production or test wiring installs the application."""

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="growth_onboarding_application_not_configured",
    )


async def get_growth_onboarding_actor_context(
    family_id: str,
    authorization: Annotated[str | None, Header()] = None,
) -> GrowthOnboardingActorContext:
    """Fail closed until a trusted identity resolver is installed."""

    del family_id, authorization
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="growth_onboarding_identity_not_configured",
    )


@router.post("/families/{family_id}/growth/onboardings")
async def start_growth_onboarding(
    family_id: str,
    body: StartGrowthOnboardingRequest,
    actor: Annotated[
        GrowthOnboardingActorContext, Depends(get_growth_onboarding_actor_context)
    ],
    application: Annotated[
        GrowthOnboardingApplication, Depends(get_growth_onboarding_application)
    ],
    idempotency_key: Annotated[str | None, Header()] = None,
    x_correlation_id: Annotated[str | None, Header()] = None,
) -> dict:
    if actor.family_id != family_id:
        raise HTTPException(status_code=403, detail="family_access_denied")
    if actor.actor_type.upper() != "HUMAN":
        raise HTTPException(status_code=403, detail="human_actor_required")
    if idempotency_key is None or not idempotency_key.strip() or len(idempotency_key) > 128:
        raise HTTPException(status_code=400, detail="invalid_idempotency_key")

    command = StartGrowthOnboardingCommand(
        tenant_id=actor.tenant_id,
        family_id=actor.family_id,
        actor_id=actor.actor_id,
        intent_id=body.intent_id,
        correlation_id=x_correlation_id or str(uuid4()),
        idempotency_key=idempotency_key,
    )
    try:
        response = await application.start(command)
    except JourneyValidationError as error:
        raise HTTPException(status_code=400, detail=error.code) from error
    except JourneyForbiddenError as error:
        raise HTTPException(status_code=403, detail=error.code) from error
    except JourneyNotFoundError as error:
        raise HTTPException(status_code=404, detail=error.code) from error
    except JourneyConflictError as error:
        raise HTTPException(status_code=409, detail=error.code) from error

    return response


__all__ = [
    "GrowthOnboardingActorContext",
    "StartGrowthOnboardingRequest",
    "get_growth_onboarding_actor_context",
    "get_growth_onboarding_application",
    "router",
]
