from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Message


def create_project(client: TestClient, name: str) -> dict:
    response = client.post(
        "/api/projects",
        json={"name": name, "description": f"{name} description"},
    )
    assert response.status_code == 201
    return response.json()


def create_workflow(client: TestClient, name: str) -> dict:
    response = client.post(
        "/api/workflows",
        json={
            "name": name,
            "system_prompt": f"System prompt for {name}",
            "prompt_template": f"Template for {name}",
        },
    )
    assert response.status_code == 201
    return response.json()


def attach_project_workflow(
    client: TestClient,
    project_id: str,
    workflow_id: str,
    position: int | None = None,
) -> None:
    payload = {} if position is None else {"position": position}
    response = client.put(
        f"/api/projects/{project_id}/workflows/{workflow_id}",
        json=payload,
    )
    assert response.status_code in (200, 204)


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_development_cors_accepts_local_frontend(client: TestClient) -> None:
    response = client.options(
        "/api/projects",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_global_workflow_can_be_attached_to_multiple_projects(client: TestClient) -> None:
    first_project = create_project(client, "Equity Research")
    second_project = create_project(client, "Product Research")
    workflow = create_workflow(client, "Evidence-first analyst")

    attach_project_workflow(client, first_project["id"], workflow["id"])
    attach_project_workflow(client, second_project["id"], workflow["id"])

    first_workflows = client.get(
        f"/api/projects/{first_project['id']}/workflows"
    ).json()
    second_workflows = client.get(
        f"/api/projects/{second_project['id']}/workflows"
    ).json()

    assert [item["id"] for item in first_workflows] == [workflow["id"]]
    assert [item["id"] for item in second_workflows] == [workflow["id"]]

    update = client.patch(
        f"/api/workflows/{workflow['id']}",
        json={"name": "Updated global workflow"},
    )
    assert update.status_code == 200
    assert client.get(f"/api/workflows/{workflow['id']}").json()["name"] == (
        "Updated global workflow"
    )


def test_project_workflow_attach_is_ordered_and_idempotent(client: TestClient) -> None:
    project = create_project(client, "Ordered project")
    first = create_workflow(client, "First")
    second = create_workflow(client, "Second")
    third = create_workflow(client, "Third")

    attach_project_workflow(client, project["id"], third["id"], position=20)
    attach_project_workflow(client, project["id"], second["id"], position=10)
    attach_project_workflow(client, project["id"], first["id"], position=0)

    listed = client.get(f"/api/projects/{project['id']}/workflows").json()
    assert [item["id"] for item in listed] == [
        first["id"],
        second["id"],
        third["id"],
    ]

    # PUT means upsert: reattaching changes the position instead of duplicating the row.
    attach_project_workflow(client, project["id"], third["id"], position=5)
    listed = client.get(f"/api/projects/{project['id']}/workflows").json()
    assert [item["id"] for item in listed] == [
        first["id"],
        third["id"],
        second["id"],
    ]
    assert sum(item["id"] == third["id"] for item in listed) == 1


def test_equal_workflow_positions_use_workflow_id_as_tiebreaker(
    client: TestClient,
) -> None:
    project = create_project(client, "Tie breaker")
    workflows = [create_workflow(client, name) for name in ("One", "Two", "Three")]
    for workflow in reversed(workflows):
        attach_project_workflow(client, project["id"], workflow["id"], position=4)

    listed = client.get(f"/api/projects/{project['id']}/workflows").json()
    expected_ids = sorted(
        (workflow["id"] for workflow in workflows),
        key=lambda workflow_id: UUID(workflow_id).int,
    )
    assert [item["id"] for item in listed] == expected_ids


def test_conversation_effective_workflows_are_ordered_and_deduplicated(
    client: TestClient,
) -> None:
    project = create_project(client, "Composed project")
    inherited_first = create_workflow(client, "Inherited first")
    shared = create_workflow(client, "Inherited and direct")
    direct_only = create_workflow(client, "Direct only")

    attach_project_workflow(client, project["id"], inherited_first["id"], position=0)
    attach_project_workflow(client, project["id"], shared["id"], position=10)

    response = client.post(
        "/api/conversations",
        json={
            "title": "Composed chat",
            "project_id": project["id"],
            "workflow_ids": [shared["id"], direct_only["id"], shared["id"]],
            "inherit_project_workflows": True,
        },
    )
    assert response.status_code == 201
    conversation = response.json()

    assert conversation["workflow_ids"] == [shared["id"], direct_only["id"]]
    assert conversation["effective_workflow_ids"] == [
        inherited_first["id"],
        shared["id"],
        direct_only["id"],
    ]

    reloaded = client.get(f"/api/conversations/{conversation['id']}").json()
    assert reloaded["workflow_ids"] == conversation["workflow_ids"]
    assert reloaded["effective_workflow_ids"] == conversation[
        "effective_workflow_ids"
    ]


def test_global_workflow_can_attach_to_multiple_conversations_and_detach_safely(
    client: TestClient,
) -> None:
    workflow = create_workflow(client, "Shared conversation workflow")
    first = client.post("/api/conversations", json={"title": "First chat"}).json()
    second = client.post("/api/conversations", json={"title": "Second chat"}).json()

    for conversation in (first, second):
        response = client.put(
            f"/api/conversations/{conversation['id']}/workflows/{workflow['id']}",
            json={},
        )
        assert response.status_code == 200

    assert client.get(f"/api/conversations/{first['id']}").json()[
        "workflow_ids"
    ] == [workflow["id"]]
    assert client.get(f"/api/conversations/{second['id']}").json()[
        "workflow_ids"
    ] == [workflow["id"]]

    detached = client.delete(
        f"/api/conversations/{first['id']}/workflows/{workflow['id']}"
    )
    assert detached.status_code == 204
    assert client.get(f"/api/conversations/{first['id']}").json()[
        "workflow_ids"
    ] == []
    assert client.get(f"/api/conversations/{second['id']}").json()[
        "workflow_ids"
    ] == [workflow["id"]]
    assert client.get(f"/api/workflows/{workflow['id']}").status_code == 200


def test_direct_conversation_workflow_attach_is_ordered_and_idempotent(
    client: TestClient,
) -> None:
    conversation = client.post(
        "/api/conversations", json={"title": "Ordered direct workflows"}
    ).json()
    first = create_workflow(client, "Direct first")
    second = create_workflow(client, "Direct second")
    third = create_workflow(client, "Direct third")

    attachments = ((third, 20), (first, 0), (second, 10))
    for workflow, position in attachments:
        response = client.put(
            f"/api/conversations/{conversation['id']}/workflows/{workflow['id']}",
            json={"position": position},
        )
        assert response.status_code == 200

    # Reattaching the same workflow updates its ordering metadata, not cardinality.
    response = client.put(
        f"/api/conversations/{conversation['id']}/workflows/{third['id']}",
        json={"position": 5},
    )
    assert response.status_code == 200

    listed = client.get(
        f"/api/conversations/{conversation['id']}/workflows"
    ).json()
    expected = [first["id"], third["id"], second["id"]]
    assert [item["id"] for item in listed] == expected
    assert [item["position"] for item in listed] == [0, 5, 10]
    assert client.get(f"/api/conversations/{conversation['id']}").json()[
        "workflow_ids"
    ] == expected


def test_disabling_project_inheritance_uses_only_direct_workflows(
    client: TestClient,
) -> None:
    project = create_project(client, "No inheritance")
    inherited = create_workflow(client, "Inherited")
    direct = create_workflow(client, "Direct")
    attach_project_workflow(client, project["id"], inherited["id"])

    response = client.post(
        "/api/conversations",
        json={
            "title": "Direct configuration only",
            "project_id": project["id"],
            "workflow_ids": [direct["id"]],
            "inherit_project_workflows": False,
        },
    )
    assert response.status_code == 201
    conversation = response.json()
    assert conversation["workflow_ids"] == [direct["id"]]
    assert conversation["effective_workflow_ids"] == [direct["id"]]


def test_standalone_conversation_persists_without_project_or_workflow(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/conversations",
        json={"title": "Standalone notes"},
    )
    assert response.status_code == 201
    conversation = response.json()

    assert conversation["project_id"] is None
    assert conversation["workflow_ids"] == []
    assert conversation["effective_workflow_ids"] == []
    assert conversation["main_branch_id"] is not None

    reloaded = client.get(f"/api/conversations/{conversation['id']}")
    assert reloaded.status_code == 200
    assert reloaded.json() == conversation

    standalone = client.get("/api/conversations", params={"standalone": True})
    assert standalone.status_code == 200
    assert [item["id"] for item in standalone.json()] == [conversation["id"]]


def test_conversation_search_matches_titles_and_all_message_content(
    client: TestClient,
    db_session: Session,
) -> None:
    oil_chat = client.post(
        "/api/conversations",
        json={"title": "Energy market notes"},
    ).json()
    other_chat = client.post(
        "/api/conversations",
        json={"title": "Quarterly hiring plan"},
    ).json()
    db_session.add_all(
        [
            Message(
                conversation_id=UUID(oil_chat["id"]),
                role="assistant",
                content="Crude oil inventory drawdowns can move prices quickly.",
            ),
            Message(
                conversation_id=UUID(other_chat["id"]),
                role="assistant",
                content="Discuss engineering headcount and recruiting.",
            ),
        ]
    )
    db_session.commit()

    content_match = client.get(
        "/api/conversations", params={"q": "OIL inventory"}
    )
    assert content_match.status_code == 200
    assert [item["id"] for item in content_match.json()] == [oil_chat["id"]]

    title_match = client.get(
        "/api/conversations", params={"q": "hiring plan"}
    )
    assert title_match.status_code == 200
    assert [item["id"] for item in title_match.json()] == [other_chat["id"]]

    no_match = client.get(
        "/api/conversations", params={"q": "weather forecast"}
    )
    assert no_match.status_code == 200
    assert no_match.json() == []


def test_first_effective_workflow_supplies_default_model_settings(
    client: TestClient,
) -> None:
    workflow_response = client.post(
        "/api/workflows",
        json={
            "name": "Low variance analyst",
            "model_name": "gemini-workflow-default",
            "temperature": 0.2,
        },
    )
    assert workflow_response.status_code == 201
    workflow = workflow_response.json()

    conversation_response = client.post(
        "/api/conversations",
        json={"title": "Uses workflow defaults", "workflow_ids": [workflow["id"]]},
    )
    assert conversation_response.status_code == 201
    conversation = conversation_response.json()
    assert conversation["model_name"] == "gemini-workflow-default"
    assert conversation["temperature"] == 0.2

    override_response = client.post(
        "/api/conversations",
        json={
            "title": "Explicit overrides",
            "workflow_ids": [workflow["id"]],
            "model_name": None,
            "temperature": 1.1,
        },
    )
    assert override_response.status_code == 201
    override = override_response.json()
    assert override["model_name"] is None
    assert override["temperature"] == 1.1


def test_project_deletion_preserves_conversations_and_global_workflows(
    client: TestClient,
) -> None:
    project = create_project(client, "Disposable project")
    workflow = create_workflow(client, "Durable workflow")
    attach_project_workflow(client, project["id"], workflow["id"])

    created = client.post(
        "/api/conversations",
        json={
            "title": "Durable chat",
            "project_id": project["id"],
            "workflow_ids": [workflow["id"]],
        },
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    deleted = client.delete(f"/api/projects/{project['id']}")
    assert deleted.status_code == 204

    workflow_response = client.get(f"/api/workflows/{workflow['id']}")
    assert workflow_response.status_code == 200

    conversation_response = client.get(f"/api/conversations/{conversation_id}")
    assert conversation_response.status_code == 200
    conversation = conversation_response.json()
    assert conversation["project_id"] is None
    assert conversation["workflow_ids"] == [workflow["id"]]
    assert conversation["effective_workflow_ids"] == [workflow["id"]]


def test_missing_parent_resources_return_404(client: TestClient) -> None:
    workflow = create_workflow(client, "Orphan candidate")
    response = client.put(
        "/api/projects/00000000-0000-0000-0000-000000000000/workflows/"
        f"{workflow['id']}",
        json={},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"
