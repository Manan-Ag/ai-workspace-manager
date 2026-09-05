from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation, Workflow, conversation_workflows, project_workflows


def list_project_workflows(db: Session, project_id: UUID) -> list[Workflow]:
    return list(
        db.scalars(
            select(Workflow)
            .join(
                project_workflows,
                project_workflows.c.workflow_id == Workflow.id,
            )
            .where(project_workflows.c.project_id == project_id)
            .order_by(
                project_workflows.c.position,
                Workflow.id,
            )
        )
    )


def list_direct_conversation_workflows(
    db: Session,
    conversation_id: UUID,
) -> list[Workflow]:
    return list(
        db.scalars(
            select(Workflow)
            .join(
                conversation_workflows,
                conversation_workflows.c.workflow_id == Workflow.id,
            )
            .where(conversation_workflows.c.conversation_id == conversation_id)
            .order_by(
                conversation_workflows.c.position,
                Workflow.id,
            )
        )
    )


def list_effective_workflows(
    db: Session,
    conversation: Conversation,
) -> list[Workflow]:
    """Return inherited workflows first, then direct workflows, without duplicates."""

    candidates: list[Workflow] = []
    if conversation.project_id and conversation.inherit_project_workflows:
        candidates.extend(list_project_workflows(db, conversation.project_id))
    candidates.extend(list_direct_conversation_workflows(db, conversation.id))

    seen: set[UUID] = set()
    effective: list[Workflow] = []
    for workflow in candidates:
        if workflow.id in seen:
            continue
        seen.add(workflow.id)
        effective.append(workflow)
    return effective


def build_system_instruction(
    db: Session,
    conversation: Conversation,
    *,
    branch_summary: str | None = None,
) -> str:
    sections = [
        "You are the assistant in AI Workspace Manager. Answer the user's current "
        "request directly using your normal knowledge and capabilities. The active "
        "branch context is optional background, not a boundary on what topics you may "
        "answer. If the user asks about a new or unrelated topic, answer it normally "
        "instead of saying it is absent from the supplied context. For claims about the "
        "user's earlier project decisions or conversation history, rely on the supplied "
        "branch context and never invent omitted history.",
    ]

    workflows = list_effective_workflows(db, conversation)
    if workflows:
        sections.append("ACTIVE REUSABLE WORKFLOWS")
    for workflow in workflows:
        details = [f"Workflow: {workflow.name}"]
        if workflow.description:
            details.append(f"Purpose: {workflow.description}")
        if workflow.system_prompt:
            details.append(f"Instructions: {workflow.system_prompt}")
        if workflow.prompt_template:
            details.append(
                "Reusable prompt template (apply when relevant): "
                f"{workflow.prompt_template}"
            )
        sections.append("\n".join(details))

    if branch_summary is not None:
        sections.append(
            "ACTIVE BRANCH CONTEXT SNAPSHOT\n"
            "This snapshot replaces the transcript before the branch fork. Use it when "
            "it helps with the current request. It does not restrict answers to its "
            "topics, and general knowledge may still be used. Do not invent omitted "
            "user-specific history.\n"
            f"{branch_summary or '(No earlier context was relevant to this branch.)'}"
        )
    return "\n\n".join(sections)
