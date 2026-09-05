from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.models import (
    Conversation,
    Project,
    Workflow,
    conversation_workflows,
    project_workflows,
)
from app.services.workflow_context import (
    build_system_instruction,
    list_effective_workflows,
)


def test_effective_workflow_order_matches_public_position_and_id_contract(
    db_session: Session,
) -> None:
    project = Project(name="Deterministic context")
    lower_id = Workflow(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        name="Lower ID inherited",
        system_prompt="LOWER-ID-INSTRUCTION",
    )
    higher_id = Workflow(
        id=UUID("00000000-0000-0000-0000-000000000002"),
        name="Higher ID inherited and direct",
        system_prompt="HIGHER-ID-INSTRUCTION",
    )
    direct = Workflow(
        id=UUID("00000000-0000-0000-0000-000000000003"),
        name="Direct workflow",
        system_prompt="DIRECT-INSTRUCTION",
    )
    db_session.add_all([project, lower_id, higher_id, direct])
    db_session.flush()

    earlier = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Insert the higher UUID first. created_at must not override the documented ID tie-break.
    db_session.execute(
        insert(project_workflows),
        [
            {
                "project_id": project.id,
                "workflow_id": higher_id.id,
                "position": 4,
                "created_at": earlier,
            },
            {
                "project_id": project.id,
                "workflow_id": lower_id.id,
                "position": 4,
                "created_at": earlier + timedelta(seconds=1),
            },
        ],
    )
    conversation = Conversation(
        project_id=project.id,
        title="Context order",
        inherit_project_workflows=True,
    )
    db_session.add(conversation)
    db_session.flush()
    db_session.execute(
        insert(conversation_workflows),
        [
            {
                "conversation_id": conversation.id,
                "workflow_id": higher_id.id,
                "position": 0,
                "created_at": earlier,
            },
            {
                "conversation_id": conversation.id,
                "workflow_id": direct.id,
                "position": 10,
                "created_at": earlier,
            },
        ],
    )
    db_session.commit()

    effective = list_effective_workflows(db_session, conversation)
    assert [workflow.id for workflow in effective] == [
        lower_id.id,
        higher_id.id,
        direct.id,
    ]

    instruction = build_system_instruction(db_session, conversation)
    assert instruction.index("LOWER-ID-INSTRUCTION") < instruction.index(
        "HIGHER-ID-INSTRUCTION"
    )
    assert instruction.index("HIGHER-ID-INSTRUCTION") < instruction.index(
        "DIRECT-INSTRUCTION"
    )
    assert instruction.count("HIGHER-ID-INSTRUCTION") == 1


def test_standalone_context_uses_direct_workflows_only(
    db_session: Session,
) -> None:
    direct = Workflow(name="Standalone direct", system_prompt="DIRECT-ONLY")
    conversation = Conversation(title="Standalone", inherit_project_workflows=True)
    db_session.add_all([direct, conversation])
    db_session.flush()
    db_session.execute(
        insert(conversation_workflows).values(
            conversation_id=conversation.id,
            workflow_id=direct.id,
            position=0,
        )
    )
    db_session.commit()

    assert [workflow.id for workflow in list_effective_workflows(db_session, conversation)] == [
        direct.id
    ]
    assert "DIRECT-ONLY" in build_system_instruction(db_session, conversation)


def test_branch_context_is_background_not_a_topic_restriction(
    db_session: Session,
) -> None:
    conversation = Conversation(title="Open-ended branch")
    db_session.add(conversation)
    db_session.commit()

    instruction = build_system_instruction(
        db_session,
        conversation,
        branch_summary="The earlier discussion covered crude oil pricing.",
    )

    assert "optional background, not a boundary" in instruction
    assert "new or unrelated topic, answer it normally" in instruction
    assert "does not restrict answers to its topics" in instruction
