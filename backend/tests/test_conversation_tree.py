from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    BranchSuggestion,
    Conversation,
    ConversationBranch,
    Message,
)
from app.services.conversation_tree import reconstruct_message_path


def create_conversation(db: Session, title: str = "Tree test") -> Conversation:
    conversation = Conversation(title=f"{title} {uuid4()}")
    db.add(conversation)
    db.commit()
    return conversation


def create_main_branch(
    db: Session,
    conversation: Conversation,
) -> ConversationBranch:
    branch = ConversationBranch(
        conversation_id=conversation.id,
        name="Main",
        is_main=True,
        summary_status="not_required",
    )
    db.add(branch)
    db.commit()
    return branch


def add_message(
    db: Session,
    conversation: Conversation,
    role: str,
    content: str,
    parent: Message | None = None,
) -> Message:
    message = Message(
        conversation_id=conversation.id,
        parent_message_id=parent.id if parent else None,
        role=role,
        content=content,
    )
    db.add(message)
    db.commit()
    return message


def test_branch_path_excludes_sibling_messages(db_session: Session) -> None:
    conversation = create_conversation(db_session)
    message_a = add_message(db_session, conversation, "user", "A")
    message_b = add_message(db_session, conversation, "assistant", "B", message_a)
    add_message(db_session, conversation, "user", "C", message_b)
    message_d = add_message(db_session, conversation, "user", "D", message_b)
    message_e = add_message(db_session, conversation, "assistant", "E", message_d)

    path = reconstruct_message_path(db_session, conversation.id, message_e.id)

    assert [message.content for message in path] == ["A", "B", "D", "E"]
    assert "C" not in [message.content for message in path]


def test_parent_message_cannot_cross_conversations(db_session: Session) -> None:
    first = create_conversation(db_session, "First")
    second = create_conversation(db_session, "Second")
    first_root = add_message(db_session, first, "user", "First root")

    invalid = Message(
        conversation_id=second.id,
        parent_message_id=first_root.id,
        role="user",
        content="Invalid cross-tree child",
    )
    db_session.add(invalid)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_explicit_branch_cursor_reuses_ancestry_without_copying_messages(
    db_session: Session,
) -> None:
    conversation = create_conversation(db_session)
    main = create_main_branch(db_session, conversation)
    root = add_message(db_session, conversation, "user", "A")
    shared = add_message(db_session, conversation, "assistant", "B", root)
    original_leaf = add_message(db_session, conversation, "user", "C", shared)
    main.head_message_id = original_leaf.id
    db_session.commit()

    count_before_branch = db_session.scalar(
        select(func.count(Message.id)).where(
            Message.conversation_id == conversation.id
        )
    )
    alternative = ConversationBranch(
        conversation_id=conversation.id,
        parent_branch_id=main.id,
        forked_from_message_id=shared.id,
        head_message_id=shared.id,
        name="Alternative",
        is_main=False,
        summary_status="pending",
    )
    db_session.add(alternative)
    db_session.commit()

    assert db_session.scalar(
        select(func.count(Message.id)).where(
            Message.conversation_id == conversation.id
        )
    ) == count_before_branch

    alternative_leaf = add_message(
        db_session,
        conversation,
        "user",
        "D",
        shared,
    )
    alternative.head_message_id = alternative_leaf.id
    db_session.commit()

    main_path = reconstruct_message_path(
        db_session,
        conversation.id,
        main.head_message_id,
    )
    alternative_path = reconstruct_message_path(
        db_session,
        conversation.id,
        alternative.head_message_id,
    )

    assert [message.content for message in main_path] == ["A", "B", "C"]
    assert [message.content for message in alternative_path] == ["A", "B", "D"]
    assert [message.id for message in main_path[:2]] == [
        message.id for message in alternative_path[:2]
    ]
    assert db_session.scalar(
        select(func.count(Message.id)).where(
            Message.conversation_id == conversation.id
        )
    ) == 4


def test_branch_cursor_cannot_point_into_another_conversation(
    db_session: Session,
) -> None:
    first = create_conversation(db_session, "First")
    first_main = create_main_branch(db_session, first)
    first_root = add_message(db_session, first, "user", "First root")
    second = create_conversation(db_session, "Second")

    invalid = ConversationBranch(
        conversation_id=second.id,
        parent_branch_id=first_main.id,
        forked_from_message_id=first_root.id,
        head_message_id=first_root.id,
        name="Invalid",
        is_main=False,
        summary_status="pending",
    )
    db_session.add(invalid)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_branch_summary_and_pruning_topics_persist_on_the_cursor(
    db_session: Session,
) -> None:
    conversation = create_conversation(db_session)
    main = create_main_branch(db_session, conversation)
    root = add_message(db_session, conversation, "user", "Discuss launch planning")
    side_leaf = add_message(
        db_session,
        conversation,
        "assistant",
        "Pricing and launch timing",
        root,
    )
    branch = ConversationBranch(
        conversation_id=conversation.id,
        parent_branch_id=main.id,
        forked_from_message_id=root.id,
        head_message_id=side_leaf.id,
        name="Pricing path",
        is_main=False,
        context_summary="The branch settled on annual pricing.",
        retained_topics=["annual pricing", "launch timing"],
        omitted_topics=["logo exploration"],
        summary_status="ready",
    )
    db_session.add(branch)
    db_session.commit()
    branch_id = branch.id

    db_session.expire_all()
    reloaded = db_session.get(ConversationBranch, branch_id)

    assert reloaded is not None
    assert reloaded.context_summary == "The branch settled on annual pricing."
    assert reloaded.retained_topics == ["annual pricing", "launch timing"]
    assert reloaded.omitted_topics == ["logo exploration"]
    assert reloaded.summary_status == "ready"


def test_pending_reference_suggestion_persists_without_mutating_the_tree(
    db_session: Session,
) -> None:
    conversation = create_conversation(db_session)
    main = create_main_branch(db_session, conversation)
    root = add_message(db_session, conversation, "user", "Plan the product launch")
    main_leaf = add_message(db_session, conversation, "assistant", "Main plan", root)
    main.head_message_id = main_leaf.id
    side_leaf = add_message(db_session, conversation, "assistant", "Annual pricing", root)
    side = ConversationBranch(
        conversation_id=conversation.id,
        parent_branch_id=main.id,
        forked_from_message_id=root.id,
        head_message_id=side_leaf.id,
        name="Pricing path",
        is_main=False,
        context_summary="Annual pricing was explored.",
        retained_topics=["annual pricing"],
        omitted_topics=[],
        summary_status="ready",
    )
    db_session.add(side)
    db_session.commit()
    message_count = db_session.scalar(
        select(func.count(Message.id)).where(
            Message.conversation_id == conversation.id
        )
    )

    suggestion = BranchSuggestion(
        conversation_id=conversation.id,
        source_branch_id=side.id,
        source_leaf_message_id=side_leaf.id,
        suggested_anchor_message_id=main_leaf.id,
        user_content="Use that annual pricing idea in the main plan",
        reason="The message references a retained topic from Pricing path.",
        referenced_topics=["annual pricing"],
        confidence=0.94,
        status="pending",
    )
    db_session.add(suggestion)
    db_session.commit()
    suggestion_id = suggestion.id

    db_session.expire_all()
    reloaded = db_session.get(BranchSuggestion, suggestion_id)

    assert reloaded is not None
    assert reloaded.status == "pending"
    assert reloaded.created_branch_id is None
    assert reloaded.referenced_topics == ["annual pricing"]
    assert db_session.scalar(
        select(func.count(Message.id)).where(
            Message.conversation_id == conversation.id
        )
    ) == message_count
