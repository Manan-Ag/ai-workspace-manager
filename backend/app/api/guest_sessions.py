import hashlib
import hmac
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, Depends, Header, Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models import Conversation, ConversationBranch, Message, Project

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


def _seed_tutorial_workspace(db: Session, owner_id: UUID) -> tuple[UUID, UUID, UUID]:
    project = Project(
        owner_id=owner_id,
        name="Photography workshop",
        description="A practical example showing how one plan can grow into focused branches.",
    )
    conversation = Conversation(
        owner_id=owner_id,
        project=project,
        title="Planning a beginner photography workshop",
        inherit_project_workflows=True,
    )
    db.add_all([project, conversation])
    db.flush()

    opening_question = Message(
        conversation_id=conversation.id,
        role="user",
        content=(
            "I’m organizing a weekend photography workshop for complete beginners. "
            "What should I prioritize?"
        ),
        metadata_json={"demo": True},
    )
    db.add(opening_question)
    db.flush()
    opening_answer = Message(
        conversation_id=conversation.id,
        parent_message_id=opening_question.id,
        role="assistant",
        content=(
            "Start with three priorities:\n\n"
            "1. **One clear outcome**—everyone should leave able to control exposure and composition.\n"
            "2. **Plenty of guided practice** with short exercises and immediate feedback.\n"
            "3. **Reliable logistics** including loaner cameras, charging, and an indoor backup location.\n\n"
            "Keep the group small, use plain language, and spend more time shooting than presenting."
        ),
        metadata_json={"demo": True, "generation_duration_ms": 840},
    )
    db.add(opening_answer)
    db.flush()
    main_follow_up = Message(
        conversation_id=conversation.id,
        parent_message_id=opening_answer.id,
        role="user",
        content="Turn those priorities into a simple one-week preparation plan.",
        metadata_json={"demo": True},
    )
    db.add(main_follow_up)
    db.flush()
    main_answer = Message(
        conversation_id=conversation.id,
        parent_message_id=main_follow_up.id,
        role="assistant",
        content=(
            "### One-week preparation plan\n\n"
            "- **Days 1–2:** Confirm the venue, class size, and available equipment.\n"
            "- **Days 3–4:** Build three short exercises on exposure, focus, and composition.\n"
            "- **Day 5:** Run the agenda with a friend who is new to photography.\n"
            "- **Days 6–7:** Simplify confusing sections, charge equipment, and send attendees a checklist."
        ),
        metadata_json={"demo": True, "generation_duration_ms": 720},
    )
    db.add(main_answer)
    db.flush()

    main_branch = ConversationBranch(
        conversation_id=conversation.id,
        head_message_id=main_answer.id,
        name="Main",
        is_main=True,
        summary_status="not_required",
    )
    db.add(main_branch)
    db.flush()

    branch_question = Message(
        conversation_id=conversation.id,
        parent_message_id=opening_answer.id,
        role="user",
        content="Focus only on keeping complete beginners confident during the first hour.",
        metadata_json={"demo": True},
    )
    db.add(branch_question)
    db.flush()
    branch_answer = Message(
        conversation_id=conversation.id,
        parent_message_id=branch_question.id,
        role="assistant",
        content=(
            "For a calm, beginner-friendly first hour:\n\n"
            "1. Start with camera handling and one reassuring auto-mode photo.\n"
            "2. Introduce only aperture and shutter speed using a paired exercise.\n"
            "3. Let everyone compare photos and describe one thing they like.\n"
            "4. End with a short composition walk that creates an early success."
        ),
        metadata_json={"demo": True, "generation_duration_ms": 610},
    )
    db.add(branch_answer)
    db.flush()

    sample_branch = ConversationBranch(
        conversation_id=conversation.id,
        parent_branch_id=main_branch.id,
        forked_from_message_id=opening_answer.id,
        head_message_id=branch_answer.id,
        name="Beginner-friendly first hour",
        is_main=False,
        context_summary=(
            "The user is planning a weekend photography workshop and wants to focus "
            "this path on confidence and pacing for complete beginners."
        ),
        retained_topics=["beginner confidence", "guided practice", "first-hour pacing"],
        omitted_topics=["venue logistics", "broader one-week preparation"],
        summary_status="ready",
    )
    db.add(sample_branch)
    db.commit()
    return conversation.id, main_branch.id, sample_branch.id


def require_guest_session(
    response: Response,
    guest_header: str | None = Header(default=None, alias="X-Guest-Session"),
    guest_cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
    settings: Settings = Depends(get_settings),
) -> UUID:
    guest_id = _decode_cookie(
        guest_header or guest_cookie, settings.guest_session_secret
    )
    if guest_id is None:
        guest_id = uuid4()
        _set_guest_cookie(response, guest_id, settings)
    return guest_id


@router.get("")
def get_guest_session(
    guest_header: str | None = Header(default=None, alias="X-Guest-Session"),
    guest_cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    return {
        "active": _decode_cookie(
            guest_header or guest_cookie, settings.guest_session_secret
        )
        is not None
    }


@router.post("")
def create_guest_session(
    response: Response,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
) -> dict[str, bool | str]:
    guest_id = uuid4()
    token = _encode_cookie(guest_id, settings.guest_session_secret)
    _set_guest_cookie(response, guest_id, settings)
    conversation_id, main_branch_id, sample_branch_id = _seed_tutorial_workspace(
        db, guest_id
    )
    return {
        "active": True,
        "token": token,
        "conversation_id": str(conversation_id),
        "main_branch_id": str(main_branch_id),
        "sample_branch_id": str(sample_branch_id),
    }
