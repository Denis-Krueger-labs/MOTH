"""Provide the API-token dependency used to protect MOTH endpoints."""

import hmac

from fastapi import (
    HTTPException,
    Request,
)

from app.db.events import (
    record_batched_event_safely,
)


async def require_api_token(
    request: Request,
) -> None:
    """Reject missing, malformed, or incorrect bearer tokens before route handling."""
    from app.core.config import get_api_token

    authorization = request.headers.get(
        "Authorization"
    )

    if authorization is None:
        record_batched_event_safely(
            "auth_rejected",
            code="MISSING",
            state="rejected",
            source="api",
        )

        raise HTTPException(
            status_code=401,
            detail=(
                "MORI found no authorization "
                "at the nest entrance"
            ),
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    scheme, separator, token = (
        authorization.partition(" ")
    )

    if (
        scheme.lower() != "bearer"
        or not separator
        or not token
    ):
        record_batched_event_safely(
            "auth_rejected",
            code="MALFORMED",
            state="rejected",
            source="api",
        )

        raise HTTPException(
            status_code=401,
            detail=(
                "MORI swatted away malformed "
                "authorization"
            ),
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    try:
        expected_token = get_api_token()

    except RuntimeError as exc:
        record_batched_event_safely(
            "auth_rejected",
            code="SERVER_TOKEN_MISSING",
            state="error",
            source="api",
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "MORI cannot guard the nest "
                "because MOTH_API_TOKEN is missing"
            ),
        ) from exc

    # Constant-time comparison prevents token-prefix timing leaks.
    if not hmac.compare_digest(
        token,
        expected_token,
    ):
        record_batched_event_safely(
            "auth_rejected",
            code="UNKNOWN",
            state="rejected",
            source="api",
        )

        raise HTTPException(
            status_code=401,
            detail=(
                "MORI does not recognize "
                "this visitor"
            ),
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )
