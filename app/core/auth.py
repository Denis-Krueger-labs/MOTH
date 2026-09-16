import hmac

from fastapi import HTTPException, Request


async def require_api_token(
    request: Request,
) -> None:
    from app.core.config import get_api_token

    authorization = request.headers.get(
        "Authorization"
    )

    if authorization is None:
        raise HTTPException(
            status_code=401,
            detail=(
                "MORI found no authorization "
                "at the nest entrance"
            ),
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    scheme, separator, token = authorization.partition(
        " "
    )

    if (
        scheme.lower() != "bearer"
        or not separator
        or not token
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "MORI swatted away malformed authorization"
            ),
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    try:
        expected_token = get_api_token()

    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "MORI cannot guard the nest because "
                "MOTH_API_TOKEN is missing"
            ),
        ) from exc

    if not hmac.compare_digest(
        token,
        expected_token,
    ):
        raise HTTPException(
            status_code=401,
            detail=(
                "MORI does not recognize this visitor"
            ),
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )