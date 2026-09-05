from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Message


class MessageNotFoundError(Exception):
    pass


class InvalidMessageTreeError(Exception):
    pass


def list_message_tree(db: Session, conversation_id: UUID) -> list[Message]:
    return list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
        )
    )


def reconstruct_message_path(
    db: Session,
    conversation_id: UUID,
    leaf_message_id: UUID,
) -> list[Message]:
    current = db.scalar(
        select(Message).where(
            Message.id == leaf_message_id,
            Message.conversation_id == conversation_id,
        )
    )
    if current is None:
        raise MessageNotFoundError("Message was not found in this conversation")

    reverse_path: list[Message] = []
    visited: set[UUID] = set()

    while current is not None:
        if current.id in visited:
            raise InvalidMessageTreeError("Conversation tree contains a cycle")

        visited.add(current.id)
        reverse_path.append(current)

        if current.parent_message_id is None:
            break

        current = db.scalar(
            select(Message).where(
                Message.id == current.parent_message_id,
                Message.conversation_id == conversation_id,
            )
        )
        if current is None:
            raise InvalidMessageTreeError("Conversation tree contains a missing parent")

    reverse_path.reverse()
    return reverse_path

