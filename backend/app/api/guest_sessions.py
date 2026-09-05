import hashlib
import hmac
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, Depends, Response

from app.core.config import Settings, get_settings

router = APIRouter(prefix="/guest-session", tags=["guest-session"])
COOKIE_NAME = "ai_workspace_guest"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30


def _signature(guest_id: UUID, secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"), guest_id.hex.encode("ascii"), hashlib.sha256
    ).hexdigest()


def _encode_cookie(guest_id: UUID, secret: str) -> str:
    return f"{guest_id.hex}.{_signature(guest_id, secret)}"


def _decode_cookie(value: str | None, secret: str) -> UUID | None:
    if not value:
        return None
    try:
        raw_id, supplied_signature = value.split(".", 1)
        guest_id = UUID(hex=raw_id)
    except (ValueError, AttributeError):
        return None
    if not hmac.compare_digest(_signature(guest_id, secret), supplied_signature):
        return None
    return guest_id


def _set_guest_cookie(response: Response, guest_id: UUID, settings: Settings) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=_encode_cookie(guest_id, settings.guest_session_secret),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )


def require_guest_session(
    response: Response,
    guest_cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
    settings: Settings = Depends(get_settings),
) -> UUID:
    guest_id = _decode_cookie(guest_cookie, settings.guest_session_secret)
    if guest_id is None:
        guest_id = uuid4()
        _set_guest_cookie(response, guest_id, settings)
    return guest_id


@router.get("")
def get_guest_session(
    guest_cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    return {"active": _decode_cookie(guest_cookie, settings.guest_session_secret) is not None}


@router.post("")
def create_guest_session(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    _set_guest_cookie(response, uuid4(), settings)
    return {"active": True}
