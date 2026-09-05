"""Make workflows global and add standalone conversations and explicit branches.

Revision ID: 20260903_0002
Revises: 20260902_0001
Create Date: 2026-09-03

This migration preserves the original project/workflow/conversation links by
moving them into association tables. Existing message paths are represented by
explicit branch cursors without copying or modifying message history.
"""

from datetime import datetime, timezone
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision: str = "20260903_0002"
down_revision: Union[str, None] = "20260902_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_workflows",
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "workflow_id"),
    )
    op.create_table(
        "conversation_workflows",
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("conversation_id", "workflow_id"),
    )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO project_workflows (project_id, workflow_id, position)
            SELECT project_id, id, 0 FROM workflows
            """
        )
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO conversation_workflows (conversation_id, workflow_id, position)
            SELECT id, workflow_id, 0 FROM conversations
            """
        )
    )

    op.add_column(
        "conversations", sa.Column("model_name", sa.String(length=120), nullable=True)
    )
    op.add_column(
        "conversations",
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.7"),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "inherit_project_workflows",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    connection.execute(
        sa.text(
            """
            UPDATE conversations AS c
            SET model_name = w.model_name,
                temperature = w.temperature
            FROM workflows AS w
            WHERE c.workflow_id = w.id
            """
        )
    )
    connection.execute(
        sa.text("UPDATE conversations SET inherit_project_workflows = false")
    )

    op.create_table(
        "conversation_branches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("parent_branch_id", sa.Uuid(), nullable=True),
        sa.Column("forked_from_message_id", sa.Uuid(), nullable=True),
        sa.Column("head_message_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_main", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("context_summary", sa.Text(), nullable=True),
        sa.Column("retained_topics", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("omitted_topics", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column(
            "summary_status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "summary_status IN ('not_required', 'pending', 'ready', 'failed')",
            name="ck_conversation_branches_summary_status",
        ),
        sa.CheckConstraint(
            "(is_main AND parent_branch_id IS NULL AND forked_from_message_id IS NULL) "
            "OR (NOT is_main AND parent_branch_id IS NOT NULL "
            "AND forked_from_message_id IS NOT NULL)",
            name="ck_conversation_branches_main_shape",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "forked_from_message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_conversation_branches_fork_message_same_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "head_message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_conversation_branches_head_message_same_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "parent_branch_id"],
            ["conversation_branches.conversation_id", "conversation_branches.id"],
            name="fk_conversation_branches_parent_same_conversation",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id",
            "id",
            name="uq_conversation_branches_conversation_id_id",
        ),
    )
    op.create_index(
        "ix_conversation_branches_conversation_id",
        "conversation_branches",
        ["conversation_id"],
    )
    op.create_index(
        "ix_conversation_branches_parent_branch_id",
        "conversation_branches",
        ["parent_branch_id"],
    )
    op.create_index(
        "ix_conversation_branches_forked_from_message_id",
        "conversation_branches",
        ["forked_from_message_id"],
    )
    op.create_index(
        "uq_conversation_branches_one_main",
        "conversation_branches",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("is_main IS TRUE"),
        sqlite_where=sa.text("is_main IS TRUE"),
    )

    now = datetime.now(timezone.utc)
    conversation_ids = list(
        connection.execute(sa.text("SELECT id FROM conversations")).scalars()
    )
    for conversation_id in conversation_ids:
        message_rows = list(
            connection.execute(
                sa.text(
                    """
                    SELECT id, parent_message_id, created_at
                    FROM messages
                    WHERE conversation_id = :conversation_id
                    ORDER BY created_at, id
                    """
                ),
                {"conversation_id": conversation_id},
            ).mappings()
        )
        parent_ids = {
            row["parent_message_id"]
            for row in message_rows
            if row["parent_message_id"] is not None
        }
        leaves = [row for row in message_rows if row["id"] not in parent_ids]
        main_leaf_id = leaves[0]["id"] if leaves else None
        main_branch_id = uuid4()
        connection.execute(
            sa.text(
                """
                INSERT INTO conversation_branches (
                    id, conversation_id, head_message_id, name, is_main, summary_status,
                    retained_topics, omitted_topics, created_at, updated_at
                ) VALUES (
                    :id, :conversation_id, :head_message_id, 'Main', true, 'not_required',
                    '[]', '[]', :created_at, :updated_at
                )
                """
            ),
            {
                "id": main_branch_id,
                "conversation_id": conversation_id,
                "head_message_id": main_leaf_id,
                "created_at": now,
                "updated_at": now,
            },
        )

        if len(leaves) > 1 and main_leaf_id is not None:
            parents = {row["id"]: row["parent_message_id"] for row in message_rows}

            def ancestor_chain(message_id: object) -> list[object]:
                chain: list[object] = []
                current = message_id
                while current is not None:
                    chain.append(current)
                    current = parents.get(current)
                chain.reverse()
                return chain

            main_chain = ancestor_chain(main_leaf_id)
            for number, leaf in enumerate(leaves[1:], start=1):
                leaf_chain = ancestor_chain(leaf["id"])
                common_ancestors = [
                    message_id
                    for message_id, main_message_id in zip(leaf_chain, main_chain)
                    if message_id == main_message_id
                ]
                fork_message_id = common_ancestors[-1] if common_ancestors else None
                if fork_message_id is None:
                    continue
                branch_id = uuid4()
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO conversation_branches (
                            id, conversation_id, parent_branch_id,
                            forked_from_message_id, head_message_id, name, is_main,
                            summary_status, retained_topics, omitted_topics,
                            created_at, updated_at
                        ) VALUES (
                            :id, :conversation_id, :parent_branch_id,
                            :forked_from_message_id, :head_message_id, :name, false,
                            'pending', '[]', '[]', :created_at, :updated_at
                        )
                        """
                    ),
                    {
                        "id": branch_id,
                        "conversation_id": conversation_id,
                        "parent_branch_id": main_branch_id,
                        "forked_from_message_id": fork_message_id,
                        "head_message_id": leaf["id"],
                        "name": f"Imported branch {number}",
                        "created_at": now,
                        "updated_at": now,
                    },
                )

    op.create_table(
        "branch_suggestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("source_branch_id", sa.Uuid(), nullable=False),
        sa.Column("source_leaf_message_id", sa.Uuid(), nullable=False),
        sa.Column("suggested_anchor_message_id", sa.Uuid(), nullable=False),
        sa.Column("created_branch_id", sa.Uuid(), nullable=True),
        sa.Column("user_content", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("referenced_topics", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'continued', 'dismissed')",
            name="ck_branch_suggestions_status",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "source_branch_id"],
            ["conversation_branches.conversation_id", "conversation_branches.id"],
            name="fk_branch_suggestions_source_branch_same_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "source_leaf_message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_branch_suggestions_source_leaf_same_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "suggested_anchor_message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_branch_suggestions_anchor_same_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id", "created_branch_id"],
            ["conversation_branches.conversation_id", "conversation_branches.id"],
            name="fk_branch_suggestions_created_branch_same_conversation",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_branch_suggestions_conversation_id",
        "branch_suggestions",
        ["conversation_id"],
    )
    op.create_index(
        "ix_branch_suggestions_source_branch_id",
        "branch_suggestions",
        ["source_branch_id"],
    )

    op.drop_constraint(
        "conversations_project_id_fkey", "conversations", type_="foreignkey"
    )
    op.alter_column("conversations", "project_id", nullable=True)
    op.create_foreign_key(
        "conversations_project_id_fkey",
        "conversations",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_index("ix_conversations_workflow_id", table_name="conversations")
    op.drop_constraint(
        "conversations_workflow_id_fkey", "conversations", type_="foreignkey"
    )
    op.drop_column("conversations", "workflow_id")

    op.drop_index("ix_workflows_project_id", table_name="workflows")
    op.drop_constraint("workflows_project_id_fkey", "workflows", type_="foreignkey")
    op.drop_column("workflows", "project_id")


def downgrade() -> None:
    raise RuntimeError(
        "This data-preserving product redesign is forward-only because global workflows "
        "and standalone conversations cannot be represented by the previous schema."
    )
