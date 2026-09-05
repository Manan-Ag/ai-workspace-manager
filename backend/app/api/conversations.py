from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.orm import Session

from app.api.deps import (
    get_conversation_or_404,
    get_project_or_404,
    get_workflow_or_404,
)
from app.api.guest_sessions import require_guest_session
from app.db.session import get_db
from app.models import (
    Conversation,
    ConversationBranch,
    Message,
    Project,
    Workflow,
    conversation_workflows,
    project_workflows,
)
from app.schemas.domain import (
    ConversationCreate,
    ConversationRead,
    ConversationUpdate,
    WorkflowAttachmentRead,
    WorkflowAttachmentUpsert,
    WorkflowRead,
)

router = APIRouter(tags=["conversations"])


def _ordered_direct_workflow_ids(
    db: Session, conversation_id: UUID
) -> list[UUID]:
    return list(
        db.scalars(
            select(conversation_workflows.c.workflow_id)
            .where(conversation_workflows.c.conversation_id == conversation_id)
            .order_by(
                conversation_workflows.c.position,
                conversation_workflows.c.workflow_id,
            )
        )
    )


def _ordered_project_workflow_ids(db: Session, project_id: UUID) -> list[UUID]:
    return list(
        db.scalars(
            select(project_workflows.c.workflow_id)
            .where(project_workflows.c.project_id == project_id)
            .order_by(project_workflows.c.position, project_workflows.c.workflow_id)
        )
    )


def _effective_workflow_ids(
    db: Session,
    conversation: Conversation,
    direct_workflow_ids: list[UUID],
) -> list[UUID]:
    ordered_ids: list[UUID] = []
    if conversation.project_id is not None and conversation.inherit_project_workflows:
        ordered_ids.extend(
            _ordered_project_workflow_ids(db, conversation.project_id)
        )
    ordered_ids.extend(direct_workflow_ids)
    return list(dict.fromkeys(ordered_ids))


def _conversation_read(db: Session, conversation: Conversation) -> ConversationRead:
    direct_workflow_ids = _ordered_direct_workflow_ids(db, conversation.id)
    main_branch_id = db.scalar(
        select(ConversationBranch.id).where(
            ConversationBranch.conversation_id == conversation.id,
            ConversationBranch.is_main.is_(True),
        )
    )
    return ConversationRead(
        id=conversation.id,
        project_id=conversation.project_id,
        title=conversation.title,
        workflow_ids=direct_workflow_ids,
        effective_workflow_ids=_effective_workflow_ids(
            db, conversation, direct_workflow_ids
        ),
        model_name=conversation.model_name,
        temperature=conversation.temperature,
        inherit_project_workflows=conversation.inherit_project_workflows,
        main_branch_id=main_branch_id,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _validate_workflows(
    db: Session, workflow_ids: list[UUID], owner_id: UUID
) -> list[Workflow]:
    return [
        get_workflow_or_404(db, workflow_id, owner_id)
        for workflow_id in workflow_ids
    ]


def _replace_conversation_workflows(
    db: Session,
    conversation_id: UUID,
    workflow_ids: list[UUID],
) -> None:
    db.execute(
        delete(conversation_workflows).where(
            conversation_workflows.c.conversation_id == conversation_id
        )
    )
    if workflow_ids:
        db.execute(
            insert(conversation_workflows),
            [
                {
                    "conversation_id": conversation_id,
                    "workflow_id": workflow_id,
                    "position": position,
                }
                for position, workflow_id in enumerate(workflow_ids)
            ],
        )


def _create_conversation(
    db: Session,
    payload: ConversationCreate,
    owner_id: UUID,
) -> ConversationRead:
    if payload.project_id is not None:
        get_project_or_404(db, payload.project_id, owner_id)
    direct_workflows = _validate_workflows(db, payload.workflow_ids, owner_id)

    effective_workflows: list[Workflow] = []
    if payload.project_id is not None and payload.inherit_project_workflows:
        for workflow_id in _ordered_project_workflow_ids(db, payload.project_id):
            workflow = db.get(Workflow, workflow_id)
            if workflow is not None:
                effective_workflows.append(workflow)
    effective_workflows.extend(direct_workflows)
    effective_workflows = list(
        {workflow.id: workflow for workflow in effective_workflows}.values()
    )

    default_workflow = effective_workflows[0] if effective_workflows else None
    model_name = payload.model_name
    if "model_name" not in payload.model_fields_set and default_workflow is not None:
        model_name = default_workflow.model_name
    temperature = payload.temperature
    if "temperature" not in payload.model_fields_set and default_workflow is not None:
        temperature = default_workflow.temperature

    conversation = Conversation(
        owner_id=owner_id,
        project_id=payload.project_id,
        title=(payload.title or "").strip() or "Untitled conversation",
        model_name=model_name,
        temperature=temperature,
        inherit_project_workflows=payload.inherit_project_workflows,
    )
    db.add(conversation)
    db.flush()
    _replace_conversation_workflows(db, conversation.id, payload.workflow_ids)

    main_branch = ConversationBranch(
        conversation_id=conversation.id,
        name="Main",
        is_main=True,
        summary_status="not_required",
    )
    db.add(main_branch)
    db.commit()
    db.refresh(conversation)
    return _conversation_read(db, conversation)


@router.get("/conversations", response_model=list[ConversationRead])
def list_all_conversations(
    project_id: UUID | None = None,
    standalone: bool = False,
    q: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    owner_id: UUID = Depends(require_guest_session),
) -> list[ConversationRead]:
    if project_id is not None and standalone:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "project_id and standalone=true cannot be combined",
        )

    statement = select(Conversation).where(Conversation.owner_id == owner_id)
    if project_id is not None:
        get_project_or_404(db, project_id, owner_id)
        statement = statement.where(Conversation.project_id == project_id)
    elif standalone:
        statement = statement.where(Conversation.project_id.is_(None))

    search_term = (q or "").strip()
    if search_term:
        escaped_term = (
            search_term.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        pattern = f"%{escaped_term}%"
        message_match = (
            select(Message.id)
            .where(
                Message.conversation_id == Conversation.id,
                Message.content.ilike(pattern, escape="\\"),
            )
            .exists()
        )
        statement = statement.where(
            or_(
                Conversation.title.ilike(pattern, escape="\\"),
                message_match,
            )
        )

    conversations = list(
        db.scalars(statement.order_by(Conversation.updated_at.desc()))
    )
    return [_conversation_read(db, conversation) for conversation in conversations]


@router.post(
    "/conversations",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    owner_id: UUID = Depends(require_guest_session),
) -> ConversationRead:
    return _create_conversation(db, payload, owner_id)


@router.get(
    "/projects/{project_id}/conversations", response_model=list[ConversationRead]
)
def list_project_conversations(
    project_id: UUID,
    db: Session = Depends(get_db),
    owner_id: UUID = Depends(require_guest_session),
) -> list[ConversationRead]:
    get_project_or_404(db, project_id, owner_id)
    conversations = list(
        db.scalars(
            select(Conversation)
            .where(
                Conversation.project_id == project_id,
                Conversation.owner_id == owner_id,
            )
            .order_by(Conversation.updated_at.desc())
        )
    )
    return [_conversation_read(db, conversation) for conversation in conversations]


@router.post(
    "/workflows/{workflow_id}/conversations",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation_from_workflow(
    workflow_id: UUID,
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    owner_id: UUID = Depends(require_guest_session),
) -> ConversationRead:
    """Compatibility route for starting a conversation from one workflow."""
    get_workflow_or_404(db, workflow_id, owner_id)
    workflow_ids = list(dict.fromkeys([workflow_id, *payload.workflow_ids]))

    project_id = payload.project_id
    if project_id is None:
        attached_project_ids = list(
            db.scalars(
                select(project_workflows.c.project_id)
                .join(Project, Project.id == project_workflows.c.project_id)
                .where(project_workflows.c.workflow_id == workflow_id)
                .where(Project.owner_id == owner_id)
                .order_by(project_workflows.c.created_at, project_workflows.c.project_id)
                .limit(2)
            )
        )
        if len(attached_project_ids) == 1:
            project_id = attached_project_ids[0]

    inherit_project_workflows = payload.inherit_project_workflows
    if "inherit_project_workflows" not in payload.model_fields_set:
        inherit_project_workflows = False

    compatible_payload = payload.model_copy(
        update={
            "project_id": project_id,
            "workflow_ids": workflow_ids,
            "inherit_project_workflows": inherit_project_workflows,
        }
    )
    return _create_conversation(db, compatible_payload, owner_id)


@router.get("/conversations/{conversation_id}", response_model=ConversationRead)
def get_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    owner_id: UUID = Depends(require_guest_session),
) -> ConversationRead:
    conversation = get_conversation_or_404(db, conversation_id, owner_id)
    return _conversation_read(db, conversation)


@router.patch("/conversations/{conversation_id}", response_model=ConversationRead)
def update_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
    owner_id: UUID = Depends(require_guest_session),
) -> ConversationRead:
    conversation = get_conversation_or_404(db, conversation_id, owner_id)
    updates = payload.model_dump(exclude_unset=True)
    workflow_ids = updates.pop("workflow_ids", None)

    if "project_id" in updates and updates["project_id"] is not None:
        get_project_or_404(db, updates["project_id"], owner_id)
    if "title" in updates:
        if updates["title"] is None or not updates["title"].strip():
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Conversation title cannot be empty",
            )
        updates["title"] = updates["title"].strip()
    if updates.get("temperature") is None:
        updates.pop("temperature", None)
    if updates.get("inherit_project_workflows") is None:
        updates.pop("inherit_project_workflows", None)

    if workflow_ids is not None:
        _validate_workflows(db, workflow_ids, owner_id)
        _replace_conversation_workflows(db, conversation.id, workflow_ids)

    for field, value in updates.items():
        setattr(conversation, field, value)
    db.commit()
    db.refresh(conversation)
    return _conversation_read(db, conversation)


@router.get(
    "/conversations/{conversation_id}/workflows",
    response_model=list[WorkflowAttachmentRead],
)
def list_conversation_workflows(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    owner_id: UUID = Depends(require_guest_session),
) -> list[WorkflowAttachmentRead]:
    get_conversation_or_404(db, conversation_id, owner_id)
    rows = db.execute(
        select(Workflow, conversation_workflows.c.position)
        .join(
            conversation_workflows,
            conversation_workflows.c.workflow_id == Workflow.id,
        )
        .where(conversation_workflows.c.conversation_id == conversation_id)
        .order_by(conversation_workflows.c.position, Workflow.id)
    ).all()
    return [
        WorkflowAttachmentRead(
            **WorkflowRead.model_validate(workflow).model_dump(),
            position=position,
        )
        for workflow, position in rows
    ]


@router.put(
    "/conversations/{conversation_id}/workflows/{workflow_id}",
    response_model=WorkflowAttachmentRead,
)
def attach_workflow_to_conversation(
    conversation_id: UUID,
    workflow_id: UUID,
    payload: WorkflowAttachmentUpsert | None = None,
    db: Session = Depends(get_db),
    owner_id: UUID = Depends(require_guest_session),
) -> WorkflowAttachmentRead:
    conversation = get_conversation_or_404(db, conversation_id, owner_id)
    workflow = get_workflow_or_404(db, workflow_id, owner_id)
    current_position = db.scalar(
        select(conversation_workflows.c.position).where(
            conversation_workflows.c.conversation_id == conversation_id,
            conversation_workflows.c.workflow_id == workflow_id,
        )
    )

    if current_position is None:
        position = payload.position if payload is not None else None
        if position is None:
            last_position = db.scalar(
                select(func.max(conversation_workflows.c.position)).where(
                    conversation_workflows.c.conversation_id == conversation_id
                )
            )
            position = (last_position if last_position is not None else -1) + 1
        db.execute(
            insert(conversation_workflows).values(
                conversation_id=conversation_id,
                workflow_id=workflow_id,
                position=position,
            )
        )
    else:
        position = (
            payload.position
            if payload is not None and payload.position is not None
            else current_position
        )
        if position != current_position:
            db.execute(
                update(conversation_workflows)
                .where(
                    conversation_workflows.c.conversation_id == conversation_id,
                    conversation_workflows.c.workflow_id == workflow_id,
                )
                .values(position=position)
            )

    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()
    return WorkflowAttachmentRead(
        **WorkflowRead.model_validate(workflow).model_dump(),
        position=position,
    )


@router.delete(
    "/conversations/{conversation_id}/workflows/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def detach_workflow_from_conversation(
    conversation_id: UUID,
    workflow_id: UUID,
    db: Session = Depends(get_db),
    owner_id: UUID = Depends(require_guest_session),
) -> Response:
    conversation = get_conversation_or_404(db, conversation_id, owner_id)
    get_workflow_or_404(db, workflow_id, owner_id)
    db.execute(
        delete(conversation_workflows).where(
            conversation_workflows.c.conversation_id == conversation_id,
            conversation_workflows.c.workflow_id == workflow_id,
        )
    )
    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    owner_id: UUID = Depends(require_guest_session),
) -> Response:
    conversation = get_conversation_or_404(db, conversation_id, owner_id)
    db.delete(conversation)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
