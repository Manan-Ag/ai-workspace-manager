from dataclasses import dataclass
from time import perf_counter
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BranchSuggestion,
    Conversation,
    ConversationBranch,
    Message,
)
from app.models.domain import utc_now
from app.services.conversation_tree import (
    MessageNotFoundError,
    reconstruct_message_path,
)
from app.services.llm import (
    BranchSummary,
    ChatMessage,
    LLMProvider,
    ProviderError,
)
from app.services.workflow_context import build_system_instruction


class BranchNotFoundError(LookupError):
    pass


class BranchValidationError(ValueError):
    pass


class BranchConflictError(RuntimeError):
    pass


class SuggestionNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class CompletedTurn:
    branch: ConversationBranch
    user_message: Message
    assistant_message: Message


@dataclass(frozen=True)
class SuggestedTurn:
    branch: ConversationBranch
    suggestion: BranchSuggestion


TurnResult = CompletedTurn | SuggestedTurn


def get_branch(
    db: Session,
    conversation_id: UUID,
    branch_id: UUID,
) -> ConversationBranch:
    branch = db.scalar(
        select(ConversationBranch).where(
            ConversationBranch.id == branch_id,
            ConversationBranch.conversation_id == conversation_id,
        )
    )
    if branch is None:
        raise BranchNotFoundError("Branch not found")
    return branch


def get_main_branch(db: Session, conversation_id: UUID) -> ConversationBranch:
    branch = db.scalar(
        select(ConversationBranch).where(
            ConversationBranch.conversation_id == conversation_id,
            ConversationBranch.is_main.is_(True),
        )
    )
    if branch is None:
        raise BranchNotFoundError("Main branch not found")
    return branch


def list_branches(db: Session, conversation_id: UUID) -> list[ConversationBranch]:
    return list(
        db.scalars(
            select(ConversationBranch)
            .where(ConversationBranch.conversation_id == conversation_id)
            .order_by(
                ConversationBranch.is_main.desc(),
                ConversationBranch.created_at,
                ConversationBranch.id,
            )
        )
    )


def _raw_path(
    db: Session,
    conversation_id: UUID,
    leaf_message_id: UUID | None,
) -> list[Message]:
    if leaf_message_id is None:
        return []
    return reconstruct_message_path(db, conversation_id, leaf_message_id)


def list_visible_branch_messages(
    db: Session,
    branch: ConversationBranch,
) -> list[Message]:
    """Return the selected answer and messages added on this branch."""

    path = _raw_path(db, branch.conversation_id, branch.head_message_id)
    if branch.is_main:
        return path

    for index, message in enumerate(path):
        if message.id == branch.forked_from_message_id:
            return path[index:]
    raise BranchValidationError("Branch fork is not an ancestor of its head")


def _as_chat_messages(messages: list[Message]) -> list[ChatMessage]:
    return [
        ChatMessage(role=message.role, content=message.content)
        for message in messages
        if message.role in {"user", "assistant"}
    ]


def _validate_fork_anchor(
    db: Session,
    source_branch: ConversationBranch,
    forked_from_message_id: UUID,
) -> list[Message]:
    path = _raw_path(db, source_branch.conversation_id, source_branch.head_message_id)
    anchor_index = next(
        (index for index, item in enumerate(path) if item.id == forked_from_message_id),
        None,
    )
    if anchor_index is None:
        raise BranchValidationError(
            "The fork message is not on the selected source branch"
        )
    if path[anchor_index].role != "assistant":
        raise BranchValidationError("Branches must start from an assistant answer")
    return path[: anchor_index + 1]


def _summary_source_history(
    source_branch: ConversationBranch,
    source_path: list[Message],
) -> list[ChatMessage]:
    """Expose only the source branch's active context to a nested summarizer."""

    if source_branch.is_main or source_branch.summary_status != "ready":
        return _as_chat_messages(source_path)

    fork_index = next(
        (
            index
            for index, message in enumerate(source_path)
            if message.id == source_branch.forked_from_message_id
        ),
        None,
    )
    if fork_index is None:
        raise BranchValidationError("Source branch fork is not on the selected path")

    snapshot = source_branch.context_summary or "No earlier context was retained."
    return [
        ChatMessage(
            role="context",
            content=f"Source branch context snapshot:\n{snapshot}",
        ),
        *_as_chat_messages(source_path[fork_index + 1 :]),
    ]


def _top_level_main_anchor(
    db: Session,
    branch: ConversationBranch,
) -> UUID:
    current = branch
    visited: set[UUID] = set()
    while True:
        if current.id in visited:
            raise BranchValidationError("Branch hierarchy contains a cycle")
        visited.add(current.id)

        if current.parent_branch_id is None:
            raise BranchValidationError("A non-main branch is detached from the main trunk")
        parent = get_branch(db, current.conversation_id, current.parent_branch_id)
        if parent.is_main:
            if current.forked_from_message_id is None:
                raise BranchValidationError("Branch is missing its fork message")
            return current.forked_from_message_id
        current = parent


def _active_summary(branch: ConversationBranch) -> BranchSummary:
    return BranchSummary(
        summary=branch.context_summary or "",
        retained_topics=branch.retained_topics,
        omitted_topics=branch.omitted_topics,
    )


def include_omitted_topics(
    db: Session,
    *,
    conversation: Conversation,
    branch: ConversationBranch,
    topics: list[str],
    provider: LLMProvider,
) -> ConversationBranch:
    branch = _lock_branch(db, branch)
    if branch.is_main:
        raise BranchValidationError("The main branch already uses its full history")
    if branch.summary_status != "ready":
        raise BranchConflictError("The branch context is not ready to edit")
    if branch.parent_branch_id is None or branch.forked_from_message_id is None:
        raise BranchValidationError("Branch is missing its source context")

    selected = list(dict.fromkeys(topic.strip() for topic in topics if topic.strip()))
    omitted = set(branch.omitted_topics)
    unknown = [topic for topic in selected if topic not in omitted]
    if not selected:
        raise BranchValidationError("Select at least one omitted topic")
    if unknown:
        raise BranchValidationError(
            f"These topics are not currently omitted: {', '.join(unknown)}"
        )

    source_branch = get_branch(db, conversation.id, branch.parent_branch_id)
    source_path = _validate_fork_anchor(
        db,
        source_branch,
        branch.forked_from_message_id,
    )
    expanded = provider.expand_branch_context(
        source_history=_summary_source_history(source_branch, source_path),
        active_summary=_active_summary(branch),
        selected_topics=selected,
        model_name=conversation.model_name,
    )

    retained_topics = list(dict.fromkeys([*expanded.retained_topics, *selected]))
    branch.context_summary = expanded.summary
    branch.retained_topics = retained_topics
    branch.omitted_topics = [
        topic for topic in expanded.omitted_topics if topic not in selected
    ]
    branch.updated_at = utc_now()
    conversation.updated_at = utc_now()
    db.add_all([branch, conversation])
    db.commit()
    db.refresh(branch)
    return branch


def _ensure_expected_head(
    branch: ConversationBranch,
    expected_head_message_id: UUID | None,
    *,
    enforce: bool,
) -> None:
    if enforce and expected_head_message_id != branch.head_message_id:
        raise BranchConflictError(
            "This branch changed since it was loaded. Refresh before sending."
        )


def _lock_branch(db: Session, branch: ConversationBranch) -> ConversationBranch:
    locked = db.scalar(
        select(ConversationBranch)
        .where(
            ConversationBranch.id == branch.id,
            ConversationBranch.conversation_id == branch.conversation_id,
        )
        .with_for_update()
    )
    if locked is None:
        raise BranchNotFoundError("Branch not found")
    return locked


def _generate_and_store_turn(
    db: Session,
    *,
    conversation: Conversation,
    branch: ConversationBranch,
    content: str,
    provider: LLMProvider,
    reference_check_unavailable: bool = False,
    commit: bool = True,
) -> CompletedTurn:
    visible_messages = list_visible_branch_messages(db, branch)
    provider_messages = _as_chat_messages(visible_messages)
    provider_messages.append(ChatMessage(role="user", content=content))

    generation_started = perf_counter()
    assistant_content = provider.generate_response(
        messages=provider_messages,
        system_instruction=build_system_instruction(
            db,
            conversation,
            branch_summary=None if branch.is_main else branch.context_summary or "",
        ),
        model_name=conversation.model_name,
        temperature=conversation.temperature,
    ).strip()
    generation_duration_ms = round((perf_counter() - generation_started) * 1000)
    if not assistant_content:
        raise ProviderError("Gemini returned an empty assistant response")

    metadata = {}
    if reference_check_unavailable:
        metadata["reference_check"] = "unavailable"
    user_message = Message(
        id=uuid4(),
        conversation_id=conversation.id,
        parent_message_id=branch.head_message_id,
        role="user",
        content=content,
        metadata_json=metadata,
    )
    assistant_message = Message(
        id=uuid4(),
        conversation_id=conversation.id,
        parent_message_id=user_message.id,
        role="assistant",
        content=assistant_content,
        metadata_json={"generation_duration_ms": generation_duration_ms},
    )
    # These explicit flushes enforce self-referential message ordering and ensure
    # a branch cursor never points at a row the database has not seen yet.
    db.add(user_message)
    db.flush()
    db.add(assistant_message)
    db.flush()
    branch.head_message_id = assistant_message.id
    conversation.updated_at = utc_now()
    db.add_all([branch, conversation])
    if commit:
        db.commit()
        db.refresh(branch)
        db.refresh(user_message)
        db.refresh(assistant_message)
    else:
        db.flush()
    return CompletedTurn(branch, user_message, assistant_message)


def _clean_title(value: str, fallback: str, *, limit: int) -> str:
    title = " ".join(value.split()).strip(" \t\r\n\"'")
    return (title[:limit].rstrip() or fallback)[:limit]


def create_branch(
    db: Session,
    *,
    source_branch: ConversationBranch,
    forked_from_message_id: UUID,
    name: str,
    commit: bool = True,
) -> ConversationBranch:
    """Create a branch cursor immediately without waiting for Gemini."""

    _validate_fork_anchor(db, source_branch, forked_from_message_id)
    branch = ConversationBranch(
        id=uuid4(),
        conversation_id=source_branch.conversation_id,
        parent_branch_id=source_branch.id,
        forked_from_message_id=forked_from_message_id,
        head_message_id=forked_from_message_id,
        name=name.strip() or "New branch",
        is_main=False,
        summary_status="pending",
    )
    db.add(branch)
    if commit:
        db.commit()
        db.refresh(branch)
    else:
        db.flush()
    return branch


def refresh_branch_titles(
    db: Session,
    *,
    conversation: Conversation,
    branch: ConversationBranch,
    provider: LLMProvider,
) -> None:
    """Name a newly created branch and rebuild the conversation title once."""

    if branch.is_main:
        return
    if branch.forked_from_message_id is None or branch.parent_branch_id is None:
        raise BranchValidationError("Branch is missing its fork context")
    source_branch = get_branch(db, conversation.id, branch.parent_branch_id)
    source_path = _validate_fork_anchor(
        db, source_branch, branch.forked_from_message_id
    )
    context = _summary_source_history(source_branch, source_path)[-6:]
    titles = provider.generate_titles(
        branch_context=context,
        branch_names=[
            item.name
            for item in list_branches(db, conversation.id)
            if not item.is_main and item.id != branch.id
        ],
        conversation_title=conversation.title,
        model_name=conversation.model_name,
    )
    branch.name = _clean_title(titles.branch_title, branch.name, limit=120)
    conversation.title = _clean_title(
        titles.conversation_title,
        conversation.title,
        limit=200,
    )
    conversation.updated_at = utc_now()
    db.add_all([branch, conversation])
    db.commit()


def refresh_initial_conversation_title(
    db: Session,
    *,
    conversation: Conversation,
    main_branch: ConversationBranch,
    provider: LLMProvider,
) -> None:
    """Name a conversation from its first completed exchange on the main branch."""

    if not main_branch.is_main:
        raise BranchValidationError("Initial conversation titles require the main branch")
    context = _as_chat_messages(list_visible_branch_messages(db, main_branch))[-2:]
    if not context:
        return
    titles = provider.generate_titles(
        branch_context=context,
        branch_names=[],
        conversation_title=conversation.title,
        model_name=conversation.model_name,
    )
    conversation.title = _clean_title(
        titles.conversation_title,
        conversation.title,
        limit=200,
    )
    conversation.updated_at = utc_now()
    db.add(conversation)
    db.commit()


def _prepare_pending_summary(
    db: Session,
    *,
    conversation: Conversation,
    branch: ConversationBranch,
    content: str,
    provider: LLMProvider,
) -> bool:
    if branch.is_main or branch.summary_status == "ready":
        return False
    if branch.forked_from_message_id is None or branch.parent_branch_id is None:
        raise BranchValidationError("Branch is missing its fork message")
    source_branch = get_branch(
        db, conversation.id, branch.parent_branch_id
    )
    source_path = _validate_fork_anchor(
        db, source_branch, branch.forked_from_message_id
    )
    summary = provider.summarize_branch(
        source_history=_summary_source_history(source_branch, source_path),
        branch_goal=content,
        model_name=conversation.model_name,
    )
    branch.context_summary = summary.summary
    branch.retained_topics = summary.retained_topics
    branch.omitted_topics = summary.omitted_topics
    branch.summary_status = "ready"
    return True


def _find_existing_suggestion(
    db: Session,
    *,
    branch: ConversationBranch,
    content: str,
) -> BranchSuggestion | None:
    if branch.head_message_id is None:
        return None
    return db.scalar(
        select(BranchSuggestion).where(
            BranchSuggestion.conversation_id == branch.conversation_id,
            BranchSuggestion.source_branch_id == branch.id,
            BranchSuggestion.source_leaf_message_id == branch.head_message_id,
            BranchSuggestion.user_content == content,
            BranchSuggestion.status == "pending",
        )
    )


def send_message(
    db: Session,
    *,
    conversation: Conversation,
    branch: ConversationBranch,
    content: str,
    provider: LLMProvider,
    expected_head_message_id: UUID | None = None,
    enforce_expected_head: bool = False,
    skip_reference_check: bool = False,
    commit: bool = True,
) -> TurnResult:
    branch = _lock_branch(db, branch)
    _ensure_expected_head(
        branch,
        expected_head_message_id,
        enforce=enforce_expected_head,
    )
    prepared_first_summary = _prepare_pending_summary(
        db,
        conversation=conversation,
        branch=branch,
        content=content,
        provider=provider,
    )

    reference_check_unavailable = False
    if (
        not branch.is_main
        and not prepared_first_summary
        and not skip_reference_check
    ):
        existing = _find_existing_suggestion(db, branch=branch, content=content)
        if existing is not None:
            return SuggestedTurn(branch, existing)

        if branch.forked_from_message_id is None or branch.head_message_id is None:
            raise BranchValidationError("Branch is missing required message cursors")
        source_history = _raw_path(
            db,
            conversation.id,
            branch.forked_from_message_id,
        )
        try:
            check = provider.detect_omitted_reference(
                user_draft=content,
                active_summary=_active_summary(branch),
                source_history=_as_chat_messages(source_history),
                model_name=conversation.model_name,
            )
        except ProviderError:
            # Detection is advisory. A temporary detector failure should not destroy a draft.
            reference_check_unavailable = True
        else:
            if check.should_rebranch:
                suggestion = BranchSuggestion(
                    conversation_id=conversation.id,
                    source_branch_id=branch.id,
                    source_leaf_message_id=branch.head_message_id,
                    suggested_anchor_message_id=_top_level_main_anchor(db, branch),
                    user_content=content,
                    reason=check.reason.strip()
                    or "This message appears to rely on context omitted from this branch.",
                    referenced_topics=check.referenced_topics,
                    confidence=check.confidence,
                    status="pending",
                )
                db.add_all([branch, suggestion])
                db.commit()
                db.refresh(branch)
                db.refresh(suggestion)
                return SuggestedTurn(branch, suggestion)

    return _generate_and_store_turn(
        db,
        conversation=conversation,
        branch=branch,
        content=content,
        provider=provider,
        reference_check_unavailable=reference_check_unavailable,
        commit=commit,
    )


def _lock_suggestion(
    db: Session,
    suggestion: BranchSuggestion,
) -> BranchSuggestion:
    locked = db.scalar(
        select(BranchSuggestion)
        .where(BranchSuggestion.id == suggestion.id)
        .with_for_update()
    )
    if locked is None:
        raise SuggestionNotFoundError("Branch suggestion not found")
    return locked


def list_suggestions(
    db: Session,
    conversation_id: UUID,
    *,
    status: str | None = None,
) -> list[BranchSuggestion]:
    query = select(BranchSuggestion).where(
        BranchSuggestion.conversation_id == conversation_id
    )
    if status is not None:
        query = query.where(BranchSuggestion.status == status)
    return list(
        db.scalars(
            query.order_by(BranchSuggestion.created_at.desc(), BranchSuggestion.id)
        )
    )


def get_suggestion(
    db: Session,
    conversation_id: UUID,
    suggestion_id: UUID,
) -> BranchSuggestion:
    suggestion = db.scalar(
        select(BranchSuggestion).where(
            BranchSuggestion.id == suggestion_id,
            BranchSuggestion.conversation_id == conversation_id,
        )
    )
    if suggestion is None:
        raise SuggestionNotFoundError("Branch suggestion not found")
    return suggestion


def accept_suggestion(
    db: Session,
    *,
    conversation: Conversation,
    suggestion: BranchSuggestion,
    provider: LLMProvider,
) -> CompletedTurn:
    suggestion = _lock_suggestion(db, suggestion)
    if suggestion.status != "pending":
        raise BranchConflictError("Branch suggestion has already been resolved")
    main_branch = get_main_branch(db, conversation.id)
    topic = suggestion.referenced_topics[0] if suggestion.referenced_topics else "context"
    branch = create_branch(
        db,
        source_branch=main_branch,
        forked_from_message_id=suggestion.suggested_anchor_message_id,
        name=f"Revisit: {topic}"[:120],
        commit=False,
    )
    result = send_message(
        db,
        conversation=conversation,
        branch=branch,
        content=suggestion.user_content,
        provider=provider,
        expected_head_message_id=suggestion.suggested_anchor_message_id,
        enforce_expected_head=True,
        skip_reference_check=True,
        commit=False,
    )
    if not isinstance(result, CompletedTurn):  # pragma: no cover - skip is explicit
        raise BranchConflictError("Could not start the suggested branch")
    suggestion.status = "accepted"
    suggestion.created_branch_id = result.branch.id
    db.add(suggestion)
    db.commit()
    db.refresh(result.branch)
    db.refresh(result.user_message)
    db.refresh(result.assistant_message)
    db.refresh(suggestion)
    return result


def continue_suggestion(
    db: Session,
    *,
    conversation: Conversation,
    suggestion: BranchSuggestion,
    provider: LLMProvider,
) -> CompletedTurn:
    suggestion = _lock_suggestion(db, suggestion)
    if suggestion.status != "pending":
        raise BranchConflictError("Branch suggestion has already been resolved")
    source_branch = get_branch(db, conversation.id, suggestion.source_branch_id)
    result = send_message(
        db,
        conversation=conversation,
        branch=source_branch,
        content=suggestion.user_content,
        provider=provider,
        expected_head_message_id=suggestion.source_leaf_message_id,
        enforce_expected_head=True,
        skip_reference_check=True,
        commit=False,
    )
    if not isinstance(result, CompletedTurn):  # pragma: no cover - guarded by skip flag
        raise BranchConflictError("Could not continue the original branch")
    suggestion.status = "continued"
    db.add(suggestion)
    db.commit()
    db.refresh(result.branch)
    db.refresh(result.user_message)
    db.refresh(result.assistant_message)
    db.refresh(suggestion)
    return result


def dismiss_suggestion(db: Session, suggestion: BranchSuggestion) -> BranchSuggestion:
    suggestion = _lock_suggestion(db, suggestion)
    if suggestion.status != "pending":
        raise BranchConflictError("Branch suggestion has already been resolved")
    suggestion.status = "dismissed"
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)
    return suggestion
