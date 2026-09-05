from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]
MessageContent = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100_000),
]


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(BaseModel):
    name: Name
    description: str = Field(default="", max_length=4_000)


class ProjectUpdate(BaseModel):
    name: Name | None = None
    description: str | None = Field(default=None, max_length=4_000)


class ProjectRead(ReadModel):
    id: UUID
    name: str
    description: str
    created_at: datetime
    updated_at: datetime


class WorkflowCreate(BaseModel):
    name: Name
    description: str = Field(default="", max_length=4_000)
    system_prompt: str = Field(default="", max_length=20_000)
    prompt_template: str = Field(default="", max_length=20_000)
    model_name: str | None = Field(default=None, max_length=120)
    temperature: float = Field(default=0.7, ge=0, le=2)


class WorkflowUpdate(BaseModel):
    name: Name | None = None
    description: str | None = Field(default=None, max_length=4_000)
    system_prompt: str | None = Field(default=None, max_length=20_000)
    prompt_template: str | None = Field(default=None, max_length=20_000)
    model_name: str | None = Field(default=None, max_length=120)
    temperature: float | None = Field(default=None, ge=0, le=2)


class WorkflowRead(ReadModel):
    id: UUID
    name: str
    description: str
    system_prompt: str
    prompt_template: str
    model_name: str | None
    temperature: float
    created_at: datetime
    updated_at: datetime


class WorkflowAttachmentUpsert(BaseModel):
    position: int | None = Field(default=None, ge=0)


class WorkflowAttachmentRead(WorkflowRead):
    position: int


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    project_id: UUID | None = None
    workflow_ids: list[UUID] = Field(default_factory=list, max_length=50)
    model_name: str | None = Field(default=None, max_length=120)
    temperature: float = Field(default=0.7, ge=0, le=2)
    inherit_project_workflows: bool = True

    @field_validator("workflow_ids")
    @classmethod
    def deduplicate_workflow_ids(cls, value: list[UUID]) -> list[UUID]:
        return list(dict.fromkeys(value))


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    project_id: UUID | None = None
    workflow_ids: list[UUID] | None = Field(default=None, max_length=50)
    model_name: str | None = Field(default=None, max_length=120)
    temperature: float | None = Field(default=None, ge=0, le=2)
    inherit_project_workflows: bool | None = None

    @field_validator("workflow_ids")
    @classmethod
    def deduplicate_updated_workflow_ids(
        cls, value: list[UUID] | None
    ) -> list[UUID] | None:
        if value is None:
            return None
        return list(dict.fromkeys(value))


class ConversationRead(ReadModel):
    id: UUID
    project_id: UUID | None
    title: str
    workflow_ids: list[UUID] = Field(default_factory=list)
    effective_workflow_ids: list[UUID] = Field(default_factory=list)
    model_name: str | None
    temperature: float
    inherit_project_workflows: bool
    main_branch_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class BranchRead(ReadModel):
    id: UUID
    conversation_id: UUID
    parent_branch_id: UUID | None
    forked_from_message_id: UUID | None
    head_message_id: UUID | None
    name: str
    is_main: bool
    context_summary: str | None
    retained_topics: list[str]
    omitted_topics: list[str]
    summary_status: Literal["not_required", "pending", "ready", "failed"]
    created_at: datetime
    updated_at: datetime


# Compatibility name for callers written against the foundation schema.
ConversationBranchRead = BranchRead


class MessageCreate(BaseModel):
    content: MessageContent
    expected_head_message_id: UUID | None = None


class BranchCreate(BaseModel):
    source_branch_id: UUID
    forked_from_message_id: UUID
    name: Name = "New branch"


class BranchContextInclude(BaseModel):
    topics: list[Name] = Field(min_length=1, max_length=20)


class MessageRead(ReadModel):
    id: UUID
    conversation_id: UUID
    parent_message_id: UUID | None
    role: str
    content: str
    created_at: datetime
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")


class BranchSuggestionRead(ReadModel):
    id: UUID
    conversation_id: UUID
    source_branch_id: UUID
    source_leaf_message_id: UUID
    suggested_anchor_message_id: UUID
    created_branch_id: UUID | None
    user_content: str
    reason: str
    referenced_topics: list[str]
    confidence: float
    status: Literal["pending", "accepted", "continued", "dismissed"]
    created_at: datetime
    updated_at: datetime


class CompletedTurnRead(BaseModel):
    kind: Literal["completed"] = "completed"
    branch: BranchRead
    user_message: MessageRead
    assistant_message: MessageRead


class SuggestedTurnRead(BaseModel):
    kind: Literal["branch_suggested"] = "branch_suggested"
    branch: BranchRead
    suggestion: BranchSuggestionRead


class ConversationTreeRead(BaseModel):
    conversation_id: UUID
    nodes: list[MessageRead]
