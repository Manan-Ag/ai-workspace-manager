from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


project_workflows = Table(
    "project_workflows",
    Base.metadata,
    Column(
        "project_id",
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "workflow_id",
        Uuid,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("position", Integer, default=0, nullable=False),
    Column("created_at", DateTime(timezone=True), default=utc_now, nullable=False),
)


conversation_workflows = Table(
    "conversation_workflows",
    Base.metadata,
    Column(
        "conversation_id",
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "workflow_id",
        Uuid,
        ForeignKey("workflows.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("position", Integer, default=0, nullable=False),
    Column("created_at", DateTime(timezone=True), default=utc_now, nullable=False),
)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

    workflows: Mapped[list["Workflow"]] = relationship(
        secondary=project_workflows,
        back_populates="projects",
        order_by=lambda: (project_workflows.c.position, Workflow.id),
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="project",
        passive_deletes=True,
    )


class Workflow(TimestampMixin, Base):
    __tablename__ = "workflows"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    prompt_template: Mapped[str] = mapped_column(Text, default="", nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(120))
    temperature: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)

    projects: Mapped[list[Project]] = relationship(
        secondary=project_workflows,
        back_populates="workflows",
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        secondary=conversation_workflows,
        back_populates="workflows",
    )


class Conversation(TimestampMixin, Base):
    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(120))
    temperature: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    inherit_project_workflows: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    project: Mapped[Project | None] = relationship(back_populates="conversations")
    workflows: Mapped[list[Workflow]] = relationship(
        secondary=conversation_workflows,
        back_populates="conversations",
        order_by=lambda: (conversation_workflows.c.position, Workflow.id),
    )
    branches: Mapped[list["ConversationBranch"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ConversationBranch(TimestampMixin, Base):
    __tablename__ = "conversation_branches"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "id", name="uq_conversation_branches_conversation_id_id"
        ),
        ForeignKeyConstraint(
            ["conversation_id", "parent_branch_id"],
            ["conversation_branches.conversation_id", "conversation_branches.id"],
            name="fk_conversation_branches_parent_same_conversation",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "forked_from_message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_conversation_branches_fork_message_same_conversation",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "head_message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_conversation_branches_head_message_same_conversation",
        ),
        CheckConstraint(
            "summary_status IN ('not_required', 'pending', 'ready', 'failed')",
            name="ck_conversation_branches_summary_status",
        ),
        CheckConstraint(
            "(is_main AND parent_branch_id IS NULL AND forked_from_message_id IS NULL) "
            "OR (NOT is_main AND parent_branch_id IS NOT NULL "
            "AND forked_from_message_id IS NOT NULL)",
            name="ck_conversation_branches_main_shape",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    parent_branch_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    forked_from_message_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    head_message_id: Mapped[UUID | None] = mapped_column(Uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_main: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    context_summary: Mapped[str | None] = mapped_column(Text)
    retained_topics: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    omitted_topics: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    summary_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )

    conversation: Mapped[Conversation] = relationship(back_populates="branches")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'system')", name="ck_messages_role"
        ),
        UniqueConstraint(
            "conversation_id", "id", name="uq_messages_conversation_id_id"
        ),
        ForeignKeyConstraint(
            ["conversation_id", "parent_message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_messages_parent_same_conversation",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    parent_message_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class BranchSuggestion(TimestampMixin, Base):
    __tablename__ = "branch_suggestions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'accepted', 'continued', 'dismissed')",
            name="ck_branch_suggestions_status",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "source_branch_id"],
            ["conversation_branches.conversation_id", "conversation_branches.id"],
            name="fk_branch_suggestions_source_branch_same_conversation",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "source_leaf_message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_branch_suggestions_source_leaf_same_conversation",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "suggested_anchor_message_id"],
            ["messages.conversation_id", "messages.id"],
            name="fk_branch_suggestions_anchor_same_conversation",
        ),
        ForeignKeyConstraint(
            ["conversation_id", "created_branch_id"],
            ["conversation_branches.conversation_id", "conversation_branches.id"],
            name="fk_branch_suggestions_created_branch_same_conversation",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_branch_id: Mapped[UUID] = mapped_column(Uuid, index=True, nullable=False)
    source_leaf_message_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    suggested_anchor_message_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_branch_id: Mapped[UUID | None] = mapped_column(Uuid)
    user_content: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    referenced_topics: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)


Index(
    "uq_messages_one_root",
    Message.conversation_id,
    unique=True,
    postgresql_where=Message.parent_message_id.is_(None),
    sqlite_where=Message.parent_message_id.is_(None),
)
Index(
    "uq_conversation_branches_one_main",
    ConversationBranch.conversation_id,
    unique=True,
    postgresql_where=ConversationBranch.is_main.is_(True),
    sqlite_where=ConversationBranch.is_main.is_(True),
)
