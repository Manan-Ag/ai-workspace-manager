from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session

from app.api.deps import get_project_or_404, get_workflow_or_404
from app.db.session import get_db
from app.models import Workflow, project_workflows
from app.schemas.domain import (
    WorkflowAttachmentRead,
    WorkflowAttachmentUpsert,
    WorkflowCreate,
    WorkflowRead,
    WorkflowUpdate,
)

router = APIRouter(tags=["workflows"])


def _next_project_workflow_position(db: Session, project_id: UUID) -> int:
    last_position = db.scalar(
        select(func.max(project_workflows.c.position)).where(
            project_workflows.c.project_id == project_id
        )
    )
    return (last_position if last_position is not None else -1) + 1


def _attachment_read(
    workflow: Workflow, position: int
) -> WorkflowAttachmentRead:
    return WorkflowAttachmentRead(
        **WorkflowRead.model_validate(workflow).model_dump(),
        position=position,
    )


@router.get("/workflows", response_model=list[WorkflowRead])
def list_global_workflows(db: Session = Depends(get_db)) -> list[Workflow]:
    return list(db.scalars(select(Workflow).order_by(Workflow.updated_at.desc())))


@router.post(
    "/workflows",
    response_model=WorkflowRead,
    status_code=status.HTTP_201_CREATED,
)
def create_global_workflow(
    payload: WorkflowCreate,
    db: Session = Depends(get_db),
) -> Workflow:
    workflow = Workflow(**payload.model_dump())
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return workflow


@router.get(
    "/projects/{project_id}/workflows",
    response_model=list[WorkflowAttachmentRead],
)
def list_project_workflows(
    project_id: UUID,
    db: Session = Depends(get_db),
) -> list[WorkflowAttachmentRead]:
    get_project_or_404(db, project_id)
    rows = db.execute(
        select(Workflow, project_workflows.c.position)
        .join(
            project_workflows,
            project_workflows.c.workflow_id == Workflow.id,
        )
        .where(project_workflows.c.project_id == project_id)
        .order_by(project_workflows.c.position, Workflow.id)
    ).all()
    return [_attachment_read(workflow, position) for workflow, position in rows]


@router.post(
    "/projects/{project_id}/workflows",
    response_model=WorkflowAttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_and_attach_workflow(
    project_id: UUID,
    payload: WorkflowCreate,
    db: Session = Depends(get_db),
) -> WorkflowAttachmentRead:
    """Compatibility route: create a global workflow and attach it to a project."""
    project = get_project_or_404(db, project_id)
    position = _next_project_workflow_position(db, project_id)
    workflow = Workflow(**payload.model_dump())
    db.add(workflow)
    db.flush()
    db.execute(
        insert(project_workflows).values(
            project_id=project_id,
            workflow_id=workflow.id,
            position=position,
        )
    )
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(workflow)
    return _attachment_read(workflow, position)


@router.put(
    "/projects/{project_id}/workflows/{workflow_id}",
    response_model=WorkflowAttachmentRead,
)
def attach_workflow_to_project(
    project_id: UUID,
    workflow_id: UUID,
    payload: WorkflowAttachmentUpsert | None = None,
    db: Session = Depends(get_db),
) -> WorkflowAttachmentRead:
    project = get_project_or_404(db, project_id)
    workflow = get_workflow_or_404(db, workflow_id)
    current_position = db.scalar(
        select(project_workflows.c.position).where(
            project_workflows.c.project_id == project_id,
            project_workflows.c.workflow_id == workflow_id,
        )
    )

    if current_position is None:
        position = (
            payload.position
            if payload is not None and payload.position is not None
            else _next_project_workflow_position(db, project_id)
        )
        db.execute(
            insert(project_workflows).values(
                project_id=project_id,
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
                update(project_workflows)
                .where(
                    project_workflows.c.project_id == project_id,
                    project_workflows.c.workflow_id == workflow_id,
                )
                .values(position=position)
            )

    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _attachment_read(workflow, position)


@router.delete(
    "/projects/{project_id}/workflows/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def detach_workflow_from_project(
    project_id: UUID,
    workflow_id: UUID,
    db: Session = Depends(get_db),
) -> Response:
    project = get_project_or_404(db, project_id)
    get_workflow_or_404(db, workflow_id)
    db.execute(
        delete(project_workflows).where(
            project_workflows.c.project_id == project_id,
            project_workflows.c.workflow_id == workflow_id,
        )
    )
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/workflows/{workflow_id}", response_model=WorkflowRead)
def get_workflow(workflow_id: UUID, db: Session = Depends(get_db)) -> Workflow:
    return get_workflow_or_404(db, workflow_id)


@router.patch("/workflows/{workflow_id}", response_model=WorkflowRead)
def update_workflow(
    workflow_id: UUID,
    payload: WorkflowUpdate,
    db: Session = Depends(get_db),
) -> Workflow:
    workflow = get_workflow_or_404(db, workflow_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(workflow, field, value)
    db.commit()
    db.refresh(workflow)
    return workflow


@router.delete("/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(workflow_id: UUID, db: Session = Depends(get_db)) -> Response:
    workflow = get_workflow_or_404(db, workflow_id)
    db.delete(workflow)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
