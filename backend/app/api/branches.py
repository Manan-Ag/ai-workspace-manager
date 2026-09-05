import logging
from typing import Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy.orm import Session
from sqlalchemy.engine import Connection, Engine

from app.api.deps import get_conversation_or_404
from app.api.guest_sessions import require_guest_session
from app.api.llm_deps import require_llm_provider
from app.db.session import get_db
from app.models import BranchSuggestion, Conversation, ConversationBranch, Message
from app.schemas import (
    BranchCreate,
    BranchContextInclude,
    BranchRead,
    BranchSuggestionRead,
    CompletedTurnRead,
    MessageCreate,
    MessageRead,
    SuggestedTurnRead,
)
from app.services.branch_chat import (
    BranchConflictError,
    BranchNotFoundError,
    BranchValidationError,
    CompletedTurn,
    SuggestedTurn,
    SuggestionNotFoundError,
    accept_suggestion,
    continue_suggestion,
    create_branch as create_branch_cursor,
    dismiss_suggestion,
    get_branch,
    get_suggestion,
    include_omitted_topics,
    list_branches,
    list_suggestions,
    list_visible_branch_messages,
    refresh_branch_titles,
    refresh_initial_conversation_title,
    send_message,
)
from app.services.conversation_tree import MessageNotFoundError
from app.services.llm import (
    LLMProvider,
    ProviderConfigurationError,
    ProviderError,
    ProviderRateLimitError,
)

router = APIRouter(prefix="/conversations/{conversation_id}", tags=["branches"])
logger = logging.getLogger(__name__)


def _refresh_branch_titles_in_background(
    conversation_id: UUID,
    branch_id: UUID,
    provider: LLMProvider,
    bind: Engine | Connection,
) -> None:
    with Session(bind=bind) as db:
        try:
            conversation = db.get(Conversation, conversation_id)
            branch = db.get(ConversationBranch, branch_id)
            if conversation is None or branch is None:
                return
            refresh_branch_titles(
                db,
                conversation=conversation,
                branch=branch,
                provider=provider,
            )
        except Exception as exc:
            db.rollback()
            logger.warning("Gemini title refresh failed: %s", exc)


def _refresh_initial_title_in_background(
    conversation_id: UUID,
    branch_id: UUID,
    provider: LLMProvider,
    bind: Engine | Connection,
) -> None:
    with Session(bind=bind) as db:
        try:
            conversation = db.get(Conversation, conversation_id)
            branch = db.get(ConversationBranch, branch_id)
            if conversation is None or branch is None:
                return
            refresh_initial_conversation_title(
                db,
                conversation=conversation,
                main_branch=branch,
                provider=provider,
            )
        except Exception as exc:
            db.rollback()
            logger.warning("Gemini initial conversation title failed: %s", exc)


def _turn_read(result: CompletedTurn | SuggestedTurn):
    if isinstance(result, CompletedTurn):
        return CompletedTurnRead(
            kind="completed",
            branch=BranchRead.model_validate(result.branch),
            user_message=MessageRead.model_validate(result.user_message),
            assistant_message=MessageRead.model_validate(result.assistant_message),
        )
    return SuggestedTurnRead(
        kind="branch_suggested",
        branch=BranchRead.model_validate(result.branch),
        suggestion=BranchSuggestionRead.model_validate(result.suggestion),
    )


def _raise_branch_error(exc: Exception) -> None:
    if isinstance(exc, (BranchNotFoundError, SuggestionNotFoundError, MessageNotFoundError)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    if isinstance(exc, (BranchConflictError, BranchValidationError)):
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if isinstance(exc, ProviderRateLimitError):
        logger.warning("Gemini request limit reached: %s", exc)
        retry_after = exc.retry_after_seconds
        detail = "Gemini’s request limit has been reached."
        if retry_after is not None:
            detail += f" Try again in about {retry_after} seconds."
        else:
            detail += " Try again shortly or check your Gemini quota and billing."
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail,
            headers={"Retry-After": str(retry_after)} if retry_after else None,
        ) from exc
    if isinstance(exc, ProviderConfigurationError):
        logger.warning("Gemini configuration failed: %s", exc)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            str(exc),
        ) from exc
    if isinstance(exc, ProviderError):
        logger.warning("Gemini request failed: %s", exc)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "Gemini could not complete the request. No new chat message was saved.",
        ) from exc
    raise exc


@router.get("/branches", response_model=list[BranchRead])
def get_branches(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    owner_id: UUID = Depends(require_guest_session),
) -> list[ConversationBranch]:
    get_conversation_or_404(db, conversation_id, owner_id)
    return list_branches(db, conversation_id)


@router.get("/branches/{branch_id}", response_model=BranchRead)
def get_branch_detail(
    conversation_id: UUID,
    branch_id: UUID,
    db: Session = Depends(get_db),
    owner_id: UUID = Depends(require_guest_session),
) -> ConversationBranch:
    get_conversation_or_404(db, conversation_id, owner_id)
    try:
        return get_branch(db, conversation_id, branch_id)
    except Exception as exc:
        _raise_branch_error(exc)


@router.get("/branches/{branch_id}/messages", response_model=list[MessageRead])
def get_branch_messages(
    conversation_id: UUID,
    branch_id: UUID,
    db: Session = Depends(get_db),
    owner_id: UUID = Depends(require_guest_session),
) -> list[Message]:
    get_conversation_or_404(db, conversation_id, owner_id)
    try:
        branch = get_branch(db, conversation_id, branch_id)
        return list_visible_branch_messages(db, branch)
    except Exception as exc:
        _raise_branch_error(exc)


@router.post(
    "/branches/{branch_id}/context/include",
    response_model=BranchRead,
)
def include_branch_context(
    conversation_id: UUID,
    branch_id: UUID,
    payload: BranchContextInclude,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(require_llm_provider),
    owner_id: UUID = Depends(require_guest_session),
) -> ConversationBranch:
    conversation = get_conversation_or_404(db, conversation_id, owner_id)
    try:
        branch = get_branch(db, conversation_id, branch_id)
        return include_omitted_topics(
            db,
            conversation=conversation,
            branch=branch,
            topics=payload.topics,
            provider=provider,
        )
    except Exception as exc:
        db.rollback()
        _raise_branch_error(exc)


@router.post(
    "/branches",
    response_model=BranchRead,
    status_code=status.HTTP_201_CREATED,
)
def create_branch(
    conversation_id: UUID,
    payload: BranchCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(require_llm_provider),
    owner_id: UUID = Depends(require_guest_session),
) -> ConversationBranch:
    get_conversation_or_404(db, conversation_id, owner_id)
    try:
        source_branch = get_branch(db, conversation_id, payload.source_branch_id)
        branch = create_branch_cursor(
            db,
            source_branch=source_branch,
            forked_from_message_id=payload.forked_from_message_id,
            name=payload.name,
        )
        background_tasks.add_task(
            _refresh_branch_titles_in_background,
            conversation_id,
            branch.id,
            provider,
            db.get_bind(),
        )
        return branch
    except Exception as exc:
        db.rollback()
        _raise_branch_error(exc)


@router.post(
    "/branches/{branch_id}/messages",
    response_model=CompletedTurnRead | SuggestedTurnRead,
)
def create_message(
    conversation_id: UUID,
    branch_id: UUID,
    payload: MessageCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(require_llm_provider),
    owner_id: UUID = Depends(require_guest_session),
):
    conversation = get_conversation_or_404(db, conversation_id, owner_id)
    try:
        branch = get_branch(db, conversation_id, branch_id)
        is_first_main_prompt = branch.is_main and branch.head_message_id is None
        result = send_message(
            db,
            conversation=conversation,
            branch=branch,
            content=payload.content,
            provider=provider,
            expected_head_message_id=payload.expected_head_message_id,
            enforce_expected_head=(
                "expected_head_message_id" in payload.model_fields_set
            ),
        )
        if is_first_main_prompt and isinstance(result, CompletedTurn):
            background_tasks.add_task(
                _refresh_initial_title_in_background,
                conversation_id,
                branch.id,
                provider,
                db.get_bind(),
            )
        return _turn_read(result)
    except Exception as exc:
        db.rollback()
        _raise_branch_error(exc)


@router.get("/branch-suggestions", response_model=list[BranchSuggestionRead])
def get_branch_suggestions(
    conversation_id: UUID,
    suggestion_status: Literal["pending", "accepted", "continued", "dismissed"]
    | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    owner_id: UUID = Depends(require_guest_session),
) -> list[BranchSuggestion]:
    get_conversation_or_404(db, conversation_id, owner_id)
    return list_suggestions(db, conversation_id, status=suggestion_status)


@router.post(
    "/branch-suggestions/{suggestion_id}/accept",
    response_model=CompletedTurnRead,
)
def accept_branch_suggestion(
    conversation_id: UUID,
    suggestion_id: UUID,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(require_llm_provider),
    owner_id: UUID = Depends(require_guest_session),
) -> CompletedTurnRead:
    conversation = get_conversation_or_404(db, conversation_id, owner_id)
    try:
        suggestion = get_suggestion(db, conversation_id, suggestion_id)
        return _turn_read(
            accept_suggestion(
                db,
                conversation=conversation,
                suggestion=suggestion,
                provider=provider,
            )
        )
    except Exception as exc:
        db.rollback()
        _raise_branch_error(exc)


@router.post(
    "/branch-suggestions/{suggestion_id}/continue",
    response_model=CompletedTurnRead,
)
def continue_branch_suggestion(
    conversation_id: UUID,
    suggestion_id: UUID,
    db: Session = Depends(get_db),
    provider: LLMProvider = Depends(require_llm_provider),
    owner_id: UUID = Depends(require_guest_session),
) -> CompletedTurnRead:
    conversation = get_conversation_or_404(db, conversation_id, owner_id)
    try:
        suggestion = get_suggestion(db, conversation_id, suggestion_id)
        return _turn_read(
            continue_suggestion(
                db,
                conversation=conversation,
                suggestion=suggestion,
                provider=provider,
            )
        )
    except Exception as exc:
        db.rollback()
        _raise_branch_error(exc)


@router.post(
    "/branch-suggestions/{suggestion_id}/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
)
def dismiss_branch_suggestion(
    conversation_id: UUID,
    suggestion_id: UUID,
    db: Session = Depends(get_db),
    owner_id: UUID = Depends(require_guest_session),
) -> Response:
    get_conversation_or_404(db, conversation_id, owner_id)
    try:
        suggestion = get_suggestion(db, conversation_id, suggestion_id)
        dismiss_suggestion(db, suggestion)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:
        db.rollback()
        _raise_branch_error(exc)
