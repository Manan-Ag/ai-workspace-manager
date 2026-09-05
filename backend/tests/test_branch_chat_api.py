from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.llm_deps import require_llm_provider
from app.main import app
from app.services.llm import (
    BranchSummary,
    ChatMessage,
    ProviderError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ReferenceCheck,
    TitleSuggestions,
)


@dataclass
class FakeProvider:
    summary: BranchSummary = field(
        default_factory=lambda: BranchSummary(
            summary="Keep the product constraints; omit the launch budget.",
            retained_topics=["product constraints"],
            omitted_topics=["launch budget"],
        )
    )
    reference: ReferenceCheck = field(
        default_factory=lambda: ReferenceCheck(
            should_rebranch=False,
            reason="",
            referenced_topics=[],
            confidence=0,
        )
    )
    expanded_summary: BranchSummary = field(
        default_factory=lambda: BranchSummary(
            summary="Keep the product constraints and the $50,000 launch budget.",
            retained_topics=["product constraints", "launch budget"],
            omitted_topics=[],
        )
    )
    assistant_content: str = "Fake assistant response"
    branch_title: str = "Product direction"
    conversation_title: str = "Product launch planning"
    fail_summary: bool = False
    fail_reference: bool = False
    fail_generation: bool = False
    rate_limit_generation: bool = False
    configuration_failure: bool = False
    fail_titles: bool = False
    summary_calls: list[dict[str, Any]] = field(default_factory=list)
    expansion_calls: list[dict[str, Any]] = field(default_factory=list)
    reference_calls: list[dict[str, Any]] = field(default_factory=list)
    generation_calls: list[dict[str, Any]] = field(default_factory=list)
    title_calls: list[dict[str, Any]] = field(default_factory=list)

    def summarize_branch(
        self,
        *,
        source_history: list[ChatMessage],
        branch_goal: str,
        model_name: str | None = None,
    ) -> BranchSummary:
        self.summary_calls.append(
            {
                "source_history": list(source_history),
                "branch_goal": branch_goal,
                "model_name": model_name,
            }
        )
        if self.fail_summary:
            raise ProviderError("summary unavailable")
        return self.summary

    def detect_omitted_reference(
        self,
        *,
        user_draft: str,
        active_summary: BranchSummary,
        source_history: list[ChatMessage],
        model_name: str | None = None,
    ) -> ReferenceCheck:
        self.reference_calls.append(
            {
                "user_draft": user_draft,
                "active_summary": active_summary,
                "source_history": list(source_history),
                "model_name": model_name,
            }
        )
        if self.fail_reference:
            raise ProviderError("reference detector unavailable")
        return self.reference

    def expand_branch_context(
        self,
        *,
        source_history: list[ChatMessage],
        active_summary: BranchSummary,
        selected_topics: list[str],
        model_name: str | None = None,
    ) -> BranchSummary:
        self.expansion_calls.append(
            {
                "source_history": list(source_history),
                "active_summary": active_summary,
                "selected_topics": list(selected_topics),
                "model_name": model_name,
            }
        )
        return self.expanded_summary

    def generate_response(
        self,
        *,
        messages: list[ChatMessage],
        system_instruction: str,
        model_name: str | None = None,
        temperature: float = 0.7,
    ) -> str:
        self.generation_calls.append(
            {
                "messages": list(messages),
                "system_instruction": system_instruction,
                "model_name": model_name,
                "temperature": temperature,
            }
        )
        if self.fail_generation:
            raise ProviderError("generation unavailable")
        if self.rate_limit_generation:
            raise ProviderRateLimitError(
                "quota exhausted",
                retry_after_seconds=28,
            )
        if self.configuration_failure:
            raise ProviderConfigurationError(
                "The Gemini API is disabled for this key’s project."
            )
        return self.assistant_content

    def generate_titles(
        self,
        *,
        branch_context: list[ChatMessage],
        branch_names: list[str],
        conversation_title: str,
        model_name: str | None = None,
    ) -> TitleSuggestions:
        self.title_calls.append(
            {
                "branch_context": list(branch_context),
                "branch_names": list(branch_names),
                "conversation_title": conversation_title,
                "model_name": model_name,
            }
        )
        if self.fail_titles:
            raise ProviderError("title generation unavailable")
        return TitleSuggestions(
            branch_title=self.branch_title,
            conversation_title=self.conversation_title,
        )


@pytest.fixture()
def fake_provider(client: TestClient) -> FakeProvider:
    provider = FakeProvider()
    app.dependency_overrides[require_llm_provider] = lambda: provider
    return provider


def create_conversation(client: TestClient, title: str = "Branch test") -> dict:
    response = client.post("/api/conversations", json={"title": title})
    assert response.status_code == 201
    return response.json()


def send_turn(
    client: TestClient,
    conversation_id: str,
    branch_id: str,
    content: str,
    *,
    expected_head_message_id: str | None = None,
) -> dict:
    response = client.post(
        f"/api/conversations/{conversation_id}/branches/{branch_id}/messages",
        json={
            "content": content,
            "expected_head_message_id": expected_head_message_id,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "completed"
    duration = body["assistant_message"]["metadata"]["generation_duration_ms"]
    assert isinstance(duration, int)
    assert duration >= 0
    return body


def seed_main_path(
    client: TestClient,
    conversation: dict,
) -> tuple[dict, dict]:
    first = send_turn(
        client,
        conversation["id"],
        conversation["main_branch_id"],
        "The launch budget is $50,000.",
    )
    second = send_turn(
        client,
        conversation["id"],
        conversation["main_branch_id"],
        "Now outline the launch schedule.",
        expected_head_message_id=first["assistant_message"]["id"],
    )
    return first, second


def create_side_branch(
    client: TestClient,
    conversation: dict,
    fork_message_id: str,
    *,
    content: str = "Explore only the product design constraints.",
) -> dict:
    response = client.post(
        f"/api/conversations/{conversation['id']}/branches",
        json={
            "source_branch_id": conversation["main_branch_id"],
            "forked_from_message_id": fork_message_id,
            "name": "Product design",
        },
    )
    assert response.status_code == 201
    branch = response.json()
    assert branch["summary_status"] == "pending"
    return send_turn(
        client,
        conversation["id"],
        branch["id"],
        content,
        expected_head_message_id=branch["head_message_id"],
    )


def all_messages(client: TestClient, conversation_id: str) -> list[dict]:
    response = client.get(f"/api/conversations/{conversation_id}/tree")
    assert response.status_code == 200
    return response.json()["nodes"]


def as_pairs(messages: list[ChatMessage]) -> list[tuple[str, str]]:
    return [(message.role, message.content) for message in messages]


def test_branch_summary_prunes_pre_fork_history_from_generation(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client)
    first, _ = seed_main_path(client, conversation)
    main_generation_count = len(fake_provider.generation_calls)

    branch_turn = create_side_branch(
        client,
        conversation,
        first["assistant_message"]["id"],
    )

    assert len(fake_provider.summary_calls) == 1
    summary_call = fake_provider.summary_calls[0]
    assert as_pairs(summary_call["source_history"]) == [
        ("user", "The launch budget is $50,000."),
        ("assistant", "Fake assistant response"),
    ]
    assert summary_call["branch_goal"] == (
        "Explore only the product design constraints."
    )

    branch = branch_turn["branch"]
    assert branch["context_summary"] == fake_provider.summary.summary
    assert branch["retained_topics"] == fake_provider.summary.retained_topics
    assert branch["omitted_topics"] == fake_provider.summary.omitted_topics
    assert branch["summary_status"] == "ready"

    branch_generation = fake_provider.generation_calls[main_generation_count]
    assert as_pairs(branch_generation["messages"]) == [
        ("assistant", "Fake assistant response"),
        ("user", "Explore only the product design constraints."),
    ]
    assert fake_provider.summary.summary in branch_generation["system_instruction"]
    assert "does not restrict answers to its topics" in branch_generation[
        "system_instruction"
    ]
    assert "$50,000" not in branch_generation["system_instruction"]
    assert "$50,000" not in " ".join(
        message.content for message in branch_generation["messages"]
    )

    reloaded = client.get(
        f"/api/conversations/{conversation['id']}/branches/{branch['id']}"
    )
    assert reloaded.status_code == 200
    assert reloaded.json()["context_summary"] == fake_provider.summary.summary


def test_user_can_restore_selected_omitted_topics(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client)
    first, _ = seed_main_path(client, conversation)
    branch_turn = create_side_branch(
        client,
        conversation,
        first["assistant_message"]["id"],
    )
    branch_id = branch_turn["branch"]["id"]

    response = client.post(
        f"/api/conversations/{conversation['id']}/branches/"
        f"{branch_id}/context/include",
        json={"topics": ["launch budget"]},
    )

    assert response.status_code == 200
    branch = response.json()
    assert branch["context_summary"] == fake_provider.expanded_summary.summary
    assert "launch budget" in branch["retained_topics"]
    assert "launch budget" not in branch["omitted_topics"]
    assert len(fake_provider.expansion_calls) == 1
    expansion_call = fake_provider.expansion_calls[0]
    assert expansion_call["selected_topics"] == ["launch budget"]
    assert "$50,000" in " ".join(
        message.content for message in expansion_call["source_history"]
    )


def test_only_currently_omitted_topics_can_be_restored(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client)

    response = client.post(
        f"/api/conversations/{conversation['id']}/branches/"
        f"{conversation['main_branch_id']}/context/include",
        json={"topics": ["launch budget"]},
    )

    assert response.status_code == 409
    assert "main branch already uses its full history" in response.json()["detail"]
    assert not fake_provider.expansion_calls


def test_titles_refresh_on_first_main_prompt_and_each_new_branch(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client, "Placeholder title")
    main_turn = send_turn(
        client,
        conversation["id"],
        conversation["main_branch_id"],
        "Plan a private beta.",
    )

    assert main_turn["branch"]["name"] == "Main"
    initially_titled_conversation = client.get(
        f"/api/conversations/{conversation['id']}"
    ).json()
    assert initially_titled_conversation["title"] == fake_provider.conversation_title
    assert len(fake_provider.title_calls) == 1
    initial_title_call = fake_provider.title_calls[0]
    assert initial_title_call["branch_names"] == []
    assert initial_title_call["conversation_title"] == "Placeholder title"
    assert [message.role for message in initial_title_call["branch_context"]] == [
        "user",
        "assistant",
    ]

    previous_chat_title = fake_provider.conversation_title
    fake_provider.branch_title = "Beta onboarding"
    fake_provider.conversation_title = "Private beta onboarding plan"

    created = client.post(
        f"/api/conversations/{conversation['id']}/branches",
        json={
            "source_branch_id": conversation["main_branch_id"],
            "forked_from_message_id": main_turn["assistant_message"]["id"],
            "name": "Product design",
        },
    )
    assert created.status_code == 201
    branch = client.get(
        f"/api/conversations/{conversation['id']}/branches/{created.json()['id']}"
    ).json()
    updated_conversation = client.get(
        f"/api/conversations/{conversation['id']}"
    ).json()
    assert branch["name"] == fake_provider.branch_title
    assert updated_conversation["title"] == fake_provider.conversation_title
    assert len(fake_provider.title_calls) == 2
    title_call = fake_provider.title_calls[1]
    assert title_call["branch_names"] == []
    assert title_call["conversation_title"] == previous_chat_title

    send_turn(
        client,
        conversation["id"],
        branch["id"],
        "Explore onboarding for the beta.",
        expected_head_message_id=branch["head_message_id"],
    )
    assert len(fake_provider.title_calls) == 2

    previous_chat_title = fake_provider.conversation_title
    fake_provider.branch_title = "Launch measurements"
    fake_provider.conversation_title = "Private beta launch strategy"
    second_created = client.post(
        f"/api/conversations/{conversation['id']}/branches",
        json={
            "source_branch_id": conversation["main_branch_id"],
            "forked_from_message_id": main_turn["assistant_message"]["id"],
            "name": "Temporary metrics name",
        },
    )

    assert second_created.status_code == 201
    assert len(fake_provider.title_calls) == 3
    second_title_call = fake_provider.title_calls[2]
    assert second_title_call["branch_names"] == ["Beta onboarding"]
    assert second_title_call["conversation_title"] == previous_chat_title
    second_branch = client.get(
        f"/api/conversations/{conversation['id']}/branches/"
        f"{second_created.json()['id']}"
    ).json()
    assert second_branch["name"] == "Launch measurements"
    final_conversation = client.get(
        f"/api/conversations/{conversation['id']}"
    ).json()
    assert final_conversation["title"] == "Private beta launch strategy"


def test_title_refresh_failure_does_not_block_branch_creation(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client, "Stable chat title")
    main_turn = send_turn(
        client,
        conversation["id"],
        conversation["main_branch_id"],
        "Create an answer to branch from.",
    )
    fake_provider.fail_titles = True

    created = client.post(
        f"/api/conversations/{conversation['id']}/branches",
        json={
            "source_branch_id": conversation["main_branch_id"],
            "forked_from_message_id": main_turn["assistant_message"]["id"],
            "name": "Provisional branch name",
        },
    )

    assert created.status_code == 201
    assert created.json()["name"] == "Provisional branch name"
    conversation_after = client.get(
        f"/api/conversations/{conversation['id']}"
    ).json()
    assert conversation_after["title"] == "Product launch planning"
    assert len(fake_provider.title_calls) == 2


def test_creating_branch_is_instant_and_shares_message_ancestry(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client)
    first, second = seed_main_path(client, conversation)
    before = all_messages(client, conversation["id"])
    provider_call_count = (
        len(fake_provider.summary_calls)
        + len(fake_provider.reference_calls)
        + len(fake_provider.generation_calls)
    )
    response = client.post(
        f"/api/conversations/{conversation['id']}/branches",
        json={
            "source_branch_id": conversation["main_branch_id"],
            "forked_from_message_id": first["assistant_message"]["id"],
            "name": "Product design",
        },
    )
    assert response.status_code == 201
    branch = response.json()
    after = all_messages(client, conversation["id"])

    assert len(before) == 4
    assert after == before
    assert branch["head_message_id"] == first["assistant_message"]["id"]
    assert branch["summary_status"] == "pending"
    assert (
        len(fake_provider.summary_calls)
        + len(fake_provider.reference_calls)
        + len(fake_provider.generation_calls)
    ) == provider_call_count

    main_visible = client.get(
        f"/api/conversations/{conversation['id']}/branches/"
        f"{conversation['main_branch_id']}/messages"
    ).json()
    side_visible = client.get(
        f"/api/conversations/{conversation['id']}/branches/"
        f"{branch['id']}/messages"
    ).json()
    assert [message["id"] for message in main_visible][-1] == second[
        "assistant_message"
    ]["id"]
    assert [message["id"] for message in side_visible] == [
        first["assistant_message"]["id"]
    ]

    branch_turn = send_turn(
        client,
        conversation["id"],
        branch["id"],
        "Explore only the product design constraints.",
        expected_head_message_id=branch["head_message_id"],
    )
    assert branch_turn["user_message"]["parent_message_id"] == first[
        "assistant_message"
    ]["id"]
    assert branch_turn["assistant_message"]["parent_message_id"] == branch_turn[
        "user_message"
    ]["id"]
    assert len(all_messages(client, conversation["id"])) == 6


def test_nested_branch_summarizes_parent_snapshot_not_pruned_raw_history(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client)
    first, _ = seed_main_path(client, conversation)
    side_turn = create_side_branch(
        client,
        conversation,
        first["assistant_message"]["id"],
    )
    side_follow_up = send_turn(
        client,
        conversation["id"],
        side_turn["branch"]["id"],
        "Keep exploring product constraints.",
        expected_head_message_id=side_turn["assistant_message"]["id"],
    )

    response = client.post(
        f"/api/conversations/{conversation['id']}/branches",
        json={
            "source_branch_id": side_turn["branch"]["id"],
            "forked_from_message_id": side_follow_up["assistant_message"]["id"],
            "name": "Nested product branch",
        },
    )
    assert response.status_code == 201
    nested_branch = response.json()
    send_turn(
        client,
        conversation["id"],
        nested_branch["id"],
        "Focus on materials.",
        expected_head_message_id=nested_branch["head_message_id"],
    )

    nested_source = fake_provider.summary_calls[-1]["source_history"]
    assert nested_source[0].role == "context"
    assert fake_provider.summary.summary in nested_source[0].content
    nested_text = " ".join(message.content for message in nested_source)
    assert "$50,000" not in nested_text
    assert "Explore only the product design constraints." in nested_text
    assert "Keep exploring product constraints." in nested_text


def test_omitted_reference_creates_persisted_suggestion_without_messages(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client)
    first, _ = seed_main_path(client, conversation)
    branch_turn = create_side_branch(
        client,
        conversation,
        first["assistant_message"]["id"],
    )
    fake_provider.reference = ReferenceCheck(
        should_rebranch=True,
        reason="The draft relies on the omitted launch budget.",
        referenced_topics=["launch budget"],
        confidence=0.96,
    )
    message_count = len(all_messages(client, conversation["id"]))
    generation_count = len(fake_provider.generation_calls)
    content = "Use that $50,000 budget in this design."

    response = client.post(
        f"/api/conversations/{conversation['id']}/branches/"
        f"{branch_turn['branch']['id']}/messages",
        json={
            "content": content,
            "expected_head_message_id": branch_turn["assistant_message"]["id"],
        },
    )
    assert response.status_code == 200
    body = response.json()

    assert body["kind"] == "branch_suggested"
    assert body["suggestion"]["status"] == "pending"
    assert body["suggestion"]["created_branch_id"] is None
    assert body["suggestion"]["referenced_topics"] == ["launch budget"]
    assert len(all_messages(client, conversation["id"])) == message_count
    assert len(fake_provider.generation_calls) == generation_count
    assert len(fake_provider.reference_calls) == 1
    check = fake_provider.reference_calls[0]
    assert check["user_draft"] == content
    assert check["active_summary"] == fake_provider.summary
    assert as_pairs(check["source_history"]) == [
        ("user", "The launch budget is $50,000."),
        ("assistant", "Fake assistant response"),
    ]

    pending = client.get(
        f"/api/conversations/{conversation['id']}/branch-suggestions",
        params={"status": "pending"},
    )
    assert pending.status_code == 200
    assert [item["id"] for item in pending.json()] == [body["suggestion"]["id"]]

    # Retrying an unchanged draft at the same cursor returns the persisted suggestion.
    retry = client.post(
        f"/api/conversations/{conversation['id']}/branches/"
        f"{branch_turn['branch']['id']}/messages",
        json={
            "content": content,
            "expected_head_message_id": branch_turn["assistant_message"]["id"],
        },
    )
    assert retry.status_code == 200
    assert retry.json()["suggestion"]["id"] == body["suggestion"]["id"]
    assert len(fake_provider.reference_calls) == 1
    assert len(all_messages(client, conversation["id"])) == message_count


def test_clear_reference_continues_with_summary_and_post_fork_messages_only(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client)
    first, _ = seed_main_path(client, conversation)
    source_turn = create_side_branch(
        client,
        conversation,
        first["assistant_message"]["id"],
    )
    fake_provider.reference = ReferenceCheck(
        should_rebranch=False,
        reason="The active branch already has enough context.",
        referenced_topics=[],
        confidence=0.98,
    )

    response = client.post(
        f"/api/conversations/{conversation['id']}/branches/"
        f"{source_turn['branch']['id']}/messages",
        json={
            "content": "Refine those product constraints.",
            "expected_head_message_id": source_turn["assistant_message"]["id"],
        },
    )
    assert response.status_code == 200
    assert response.json()["kind"] == "completed"
    assert len(fake_provider.reference_calls) == 1

    generation = fake_provider.generation_calls[-1]
    assert as_pairs(generation["messages"]) == [
        ("assistant", "Fake assistant response"),
        ("user", "Explore only the product design constraints."),
        ("assistant", "Fake assistant response"),
        ("user", "Refine those product constraints."),
    ]
    assert fake_provider.summary.summary in generation["system_instruction"]
    assert "Now outline the launch schedule." not in " ".join(
        message.content for message in generation["messages"]
    )
    suggestions = client.get(
        f"/api/conversations/{conversation['id']}/branch-suggestions"
    )
    assert suggestions.status_code == 200
    assert suggestions.json() == []


def test_accepting_suggestion_creates_sibling_from_original_main_anchor(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client)
    first, _ = seed_main_path(client, conversation)
    source_turn = create_side_branch(
        client,
        conversation,
        first["assistant_message"]["id"],
    )
    fake_provider.reference = ReferenceCheck(
        should_rebranch=True,
        reason="Budget context is missing.",
        referenced_topics=["launch budget"],
        confidence=0.9,
    )
    suggested = client.post(
        f"/api/conversations/{conversation['id']}/branches/"
        f"{source_turn['branch']['id']}/messages",
        json={"content": "Return to the budget assumptions."},
    ).json()["suggestion"]
    before_count = len(all_messages(client, conversation["id"]))

    accepted = client.post(
        f"/api/conversations/{conversation['id']}/branch-suggestions/"
        f"{suggested['id']}/accept"
    )
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["kind"] == "completed"
    assert body["branch"]["parent_branch_id"] == conversation["main_branch_id"]
    assert body["branch"]["forked_from_message_id"] == first[
        "assistant_message"
    ]["id"]
    assert body["branch"]["id"] != source_turn["branch"]["id"]
    assert body["user_message"]["content"] == "Return to the budget assumptions."
    assert len(all_messages(client, conversation["id"])) == before_count + 2

    persisted = client.get(
        f"/api/conversations/{conversation['id']}/branch-suggestions"
    ).json()[0]
    assert persisted["status"] == "accepted"
    assert persisted["created_branch_id"] == body["branch"]["id"]

    repeated = client.post(
        f"/api/conversations/{conversation['id']}/branch-suggestions/"
        f"{suggested['id']}/accept"
    )
    assert repeated.status_code == 409
    assert len(all_messages(client, conversation["id"])) == before_count + 2


def test_nested_branch_suggestion_accepts_at_top_level_main_anchor(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client)
    first, _ = seed_main_path(client, conversation)
    first_level = create_side_branch(
        client,
        conversation,
        first["assistant_message"]["id"],
        content="Explore a product-only direction.",
    )
    nested_response = client.post(
        f"/api/conversations/{conversation['id']}/branches",
        json={
            "source_branch_id": first_level["branch"]["id"],
            "forked_from_message_id": first_level["assistant_message"]["id"],
            "name": "Nested experiment",
        },
    )
    assert nested_response.status_code == 201
    nested_branch = nested_response.json()
    assert nested_branch["parent_branch_id"] == first_level["branch"]["id"]
    nested = send_turn(
        client,
        conversation["id"],
        nested_branch["id"],
        "Try a second-level alternative.",
        expected_head_message_id=nested_branch["head_message_id"],
    )

    fake_provider.reference = ReferenceCheck(
        should_rebranch=True,
        reason="The draft needs context from before the top-level fork.",
        referenced_topics=["launch budget"],
        confidence=0.95,
    )
    suggestion_response = client.post(
        f"/api/conversations/{conversation['id']}/branches/"
        f"{nested['branch']['id']}/messages",
        json={
            "content": "Bring back the original launch budget.",
            "expected_head_message_id": nested["assistant_message"]["id"],
        },
    )
    assert suggestion_response.status_code == 200
    suggestion = suggestion_response.json()["suggestion"]
    assert suggestion["suggested_anchor_message_id"] == first[
        "assistant_message"
    ]["id"]

    accepted = client.post(
        f"/api/conversations/{conversation['id']}/branch-suggestions/"
        f"{suggestion['id']}/accept"
    )
    assert accepted.status_code == 200
    accepted_branch = accepted.json()["branch"]
    assert accepted_branch["parent_branch_id"] == conversation["main_branch_id"]
    assert accepted_branch["forked_from_message_id"] == first[
        "assistant_message"
    ]["id"]
    assert accepted_branch["parent_branch_id"] not in {
        first_level["branch"]["id"],
        nested["branch"]["id"],
    }


def test_continuing_suggestion_bypasses_second_check_and_uses_original_branch(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client)
    first, _ = seed_main_path(client, conversation)
    source_turn = create_side_branch(
        client,
        conversation,
        first["assistant_message"]["id"],
    )
    fake_provider.reference = ReferenceCheck(
        should_rebranch=True,
        reason="Possible omitted reference.",
        referenced_topics=["launch budget"],
        confidence=0.8,
    )
    suggested = client.post(
        f"/api/conversations/{conversation['id']}/branches/"
        f"{source_turn['branch']['id']}/messages",
        json={"content": "Continue here anyway with the old budget."},
    ).json()["suggestion"]
    checks_before_continue = len(fake_provider.reference_calls)

    continued = client.post(
        f"/api/conversations/{conversation['id']}/branch-suggestions/"
        f"{suggested['id']}/continue"
    )
    assert continued.status_code == 200
    body = continued.json()
    assert body["kind"] == "completed"
    assert body["branch"]["id"] == source_turn["branch"]["id"]
    assert body["user_message"]["parent_message_id"] == source_turn[
        "assistant_message"
    ]["id"]
    assert len(fake_provider.reference_calls) == checks_before_continue

    persisted = client.get(
        f"/api/conversations/{conversation['id']}/branch-suggestions"
    ).json()[0]
    assert persisted["status"] == "continued"


def test_dismissed_suggestion_saves_no_message(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client)
    first, _ = seed_main_path(client, conversation)
    source_turn = create_side_branch(
        client,
        conversation,
        first["assistant_message"]["id"],
    )
    fake_provider.reference = ReferenceCheck(
        should_rebranch=True,
        reason="Possible omitted reference.",
        referenced_topics=["launch budget"],
        confidence=0.8,
    )
    suggested = client.post(
        f"/api/conversations/{conversation['id']}/branches/"
        f"{source_turn['branch']['id']}/messages",
        json={"content": "Maybe reuse that old budget."},
    ).json()["suggestion"]
    before_count = len(all_messages(client, conversation["id"]))

    dismissed = client.post(
        f"/api/conversations/{conversation['id']}/branch-suggestions/"
        f"{suggested['id']}/dismiss"
    )
    assert dismissed.status_code == 204
    assert len(all_messages(client, conversation["id"])) == before_count

    persisted = client.get(
        f"/api/conversations/{conversation['id']}/branch-suggestions"
    ).json()[0]
    assert persisted["status"] == "dismissed"


def test_reference_detector_failure_does_not_block_chat_turn(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client)
    first, _ = seed_main_path(client, conversation)
    source_turn = create_side_branch(
        client,
        conversation,
        first["assistant_message"]["id"],
    )
    fake_provider.fail_reference = True

    response = client.post(
        f"/api/conversations/{conversation['id']}/branches/"
        f"{source_turn['branch']['id']}/messages",
        json={"content": "A normal follow-up despite detector failure."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "completed"
    assert body["user_message"]["metadata"]["reference_check"] == "unavailable"


def test_stale_branch_cursor_rejects_send_before_calling_provider(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client)
    first = send_turn(
        client,
        conversation["id"],
        conversation["main_branch_id"],
        "First turn",
    )
    generation_count = len(fake_provider.generation_calls)
    message_count = len(all_messages(client, conversation["id"]))

    response = client.post(
        f"/api/conversations/{conversation['id']}/branches/"
        f"{conversation['main_branch_id']}/messages",
        json={
            "content": "This was composed against a stale cursor.",
            "expected_head_message_id": first["user_message"]["id"],
        },
    )
    assert response.status_code == 409
    assert len(fake_provider.generation_calls) == generation_count
    assert len(all_messages(client, conversation["id"])) == message_count


def test_generation_failure_preserves_branch_cursor_and_message_count(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client)
    first = send_turn(
        client,
        conversation["id"],
        conversation["main_branch_id"],
        "First turn",
    )
    head_before = first["assistant_message"]["id"]
    message_count = len(all_messages(client, conversation["id"]))
    fake_provider.fail_generation = True

    response = client.post(
        f"/api/conversations/{conversation['id']}/branches/"
        f"{conversation['main_branch_id']}/messages",
        json={
            "content": "This generation will fail.",
            "expected_head_message_id": head_before,
        },
    )

    assert response.status_code == 502
    assert len(all_messages(client, conversation["id"])) == message_count
    branch = client.get(
        f"/api/conversations/{conversation['id']}/branches/"
        f"{conversation['main_branch_id']}"
    ).json()
    assert branch["head_message_id"] == head_before


def test_generation_rate_limit_returns_actionable_error_without_saving_messages(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client)
    message_count = len(all_messages(client, conversation["id"]))
    fake_provider.rate_limit_generation = True

    response = client.post(
        f"/api/conversations/{conversation['id']}/branches/"
        f"{conversation['main_branch_id']}/messages",
        json={"content": "What is happening now?"},
    )

    assert response.status_code == 429
    assert response.headers["retry-after"] == "28"
    assert "Try again in about 28 seconds" in response.json()["detail"]
    assert len(all_messages(client, conversation["id"])) == message_count


def test_generation_configuration_failure_is_shown_without_saving_messages(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client)
    message_count = len(all_messages(client, conversation["id"]))
    fake_provider.configuration_failure = True

    response = client.post(
        f"/api/conversations/{conversation['id']}/branches/"
        f"{conversation['main_branch_id']}/messages",
        json={"content": "Hello"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "The Gemini API is disabled for this key’s project."
    )
    assert len(all_messages(client, conversation["id"])) == message_count


def test_summary_failure_preserves_the_instant_branch_for_retry(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client)
    first, _ = seed_main_path(client, conversation)
    branch_count = len(
        client.get(f"/api/conversations/{conversation['id']}/branches").json()
    )
    message_count = len(all_messages(client, conversation["id"]))
    fake_provider.fail_summary = True

    created = client.post(
        f"/api/conversations/{conversation['id']}/branches",
        json={
            "source_branch_id": conversation["main_branch_id"],
            "forked_from_message_id": first["assistant_message"]["id"],
            "name": "Failed branch",
        },
    )
    assert created.status_code == 201
    branch = created.json()

    response = client.post(
        f"/api/conversations/{conversation['id']}/branches/{branch['id']}/messages",
        json={
            "content": "This summary will fail.",
            "expected_head_message_id": branch["head_message_id"],
        },
    )
    assert response.status_code == 502
    assert len(
        client.get(f"/api/conversations/{conversation['id']}/branches").json()
    ) == branch_count + 1
    assert len(all_messages(client, conversation["id"])) == message_count
    reloaded = client.get(
        f"/api/conversations/{conversation['id']}/branches/{branch['id']}"
    ).json()
    assert reloaded["head_message_id"] == first["assistant_message"]["id"]
    assert reloaded["summary_status"] == "pending"


def test_branching_from_a_user_message_is_rejected(
    client: TestClient,
    fake_provider: FakeProvider,
) -> None:
    conversation = create_conversation(client)
    first, _ = seed_main_path(client, conversation)
    provider_call_count = len(fake_provider.summary_calls) + len(
        fake_provider.generation_calls
    )

    response = client.post(
        f"/api/conversations/{conversation['id']}/branches",
        json={
            "source_branch_id": conversation["main_branch_id"],
            "forked_from_message_id": first["user_message"]["id"],
            "name": "Invalid branch",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Branches must start from an assistant answer"
    assert len(fake_provider.summary_calls) + len(
        fake_provider.generation_calls
    ) == provider_call_count
