from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_conversation_or_404
from app.db.session import get_db
from app.models import Message
from app.schemas import ConversationTreeRead, MessageRead
from app.services.conversation_tree import (
    InvalidMessageTreeError,
    MessageNotFoundError,
    list_message_tree,
    reconstruct_message_path,
)

router = APIRouter(prefix="/conversations/{conversation_id}", tags=["messages"])


@router.get("/messages", response_model=list[MessageRead])
def list_messages(
    conversation_id: UUID,
    db: Session = Depends(get_db),
) -> list[Message]:
    get_conversation_or_404(db, conversation_id)
    return list_message_tree(db, conversation_id)


@router.get("/tree", response_model=ConversationTreeRead)
def get_tree(
    conversation_id: UUID,
    db: Session = Depends(get_db),
) -> ConversationTreeRead:
    get_conversation_or_404(db, conversation_id)
    return ConversationTreeRead(
        conversation_id=conversation_id,
        nodes=[MessageRead.model_validate(node) for node in list_message_tree(db, conversation_id)],
    )


@router.get("/path", response_model=list[MessageRead])
def get_path(
    conversation_id: UUID,
    leaf_message_id: UUID,
    db: Session = Depends(get_db),
) -> list[Message]:
    get_conversation_or_404(db, conversation_id)
    try:
        return reconstruct_message_path(db, conversation_id, leaf_message_id)
    except MessageNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except InvalidMessageTreeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

