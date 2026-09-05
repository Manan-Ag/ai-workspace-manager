from typing import Literal, Protocol

from pydantic import BaseModel, Field


class ProviderError(RuntimeError):
    """Raised when an LLM provider cannot complete a request."""


class ProviderConfigurationError(ProviderError):
    """Raised when the configured provider is unavailable or incomplete."""


class ProviderRateLimitError(ProviderError):
    """Raised when the provider rejects a request because its quota is exhausted."""

    def __init__(
        self,
        message: str = "Provider request limit reached",
        *,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "context"]
    content: str


class BranchSummary(BaseModel):
    summary: str = Field(
        description="Only the prior facts, decisions, and constraints relevant to the branch goal."
    )
    retained_topics: list[str] = Field(
        default_factory=list,
        description="Short labels for topics represented in the summary.",
    )
    omitted_topics: list[str] = Field(
        default_factory=list,
        description="Short labels for recognizable source topics intentionally omitted.",
    )


class ReferenceCheck(BaseModel):
    should_rebranch: bool = Field(
        description="Whether the draft materially relies on source context omitted from this branch."
    )
    reason: str = Field(
        default="",
        description="A short user-facing explanation when a fresh branch is recommended.",
    )
    referenced_topics: list[str] = Field(
        default_factory=list,
        description="Short labels for the omitted topics the draft appears to reference.",
    )
    confidence: float = Field(default=0, ge=0, le=1)


class TitleSuggestions(BaseModel):
    branch_title: str = Field(
        description="A concise title for the newly created branch's talking point."
    )
    conversation_title: str = Field(
        description="A concise umbrella title derived from all branch talking points."
    )


class LLMProvider(Protocol):
    def summarize_branch(
        self,
        *,
        source_history: list[ChatMessage],
        branch_goal: str,
        model_name: str | None = None,
    ) -> BranchSummary:
        """Create a goal-specific, lossy snapshot of the history before a fork."""

    def expand_branch_context(
        self,
        *,
        source_history: list[ChatMessage],
        active_summary: BranchSummary,
        selected_topics: list[str],
        model_name: str | None = None,
    ) -> BranchSummary:
        """Rebuild a snapshot while restoring selected topics from source history."""

    def detect_omitted_reference(
        self,
        *,
        user_draft: str,
        active_summary: BranchSummary,
        source_history: list[ChatMessage],
        model_name: str | None = None,
    ) -> ReferenceCheck:
        """Detect whether a draft depends on information removed from a branch."""

    def generate_response(
        self,
        *,
        messages: list[ChatMessage],
        system_instruction: str,
        model_name: str | None = None,
        temperature: float = 0.7,
    ) -> str:
        """Generate the next assistant response for an assembled context."""

    def generate_titles(
        self,
        *,
        branch_context: list[ChatMessage],
        branch_names: list[str],
        conversation_title: str,
        model_name: str | None = None,
    ) -> TitleSuggestions:
        """Name a new branch and refresh the conversation's umbrella title."""
