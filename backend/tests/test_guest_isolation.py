from fastapi.testclient import TestClient

from app.main import app


def test_guest_entry_and_workspace_isolation(client: TestClient) -> None:
    assert client.get("/api/guest-session").json() == {"active": False}
    created_session = client.post("/api/guest-session").json()
    assert created_session["active"] is True
    assert created_session["token"]
    assert client.get("/api/guest-session").json() == {"active": True}
    sample_conversation = client.get(
        f"/api/conversations/{created_session['conversation_id']}"
    )
    assert sample_conversation.status_code == 200
    assert sample_conversation.json()["title"] == (
        "Planning a beginner photography workshop"
    )
    sample_branches = client.get(
        f"/api/conversations/{created_session['conversation_id']}/branches"
    ).json()
    assert {branch["name"] for branch in sample_branches} == {
        "Main",
        "Beginner-friendly first hour",
    }

    first_project = client.post(
        "/api/projects",
        json={"name": "First guest project", "description": "First guest only"},
    )
    assert first_project.status_code == 201

    with TestClient(app) as second_guest:
        assert second_guest.post("/api/guest-session").status_code == 200
        assert [
            project["name"] for project in second_guest.get("/api/projects").json()
        ] == ["Photography workshop"]
        assert (
            second_guest.get(f"/api/projects/{first_project.json()['id']}").status_code
            == 404
        )

        second_project = second_guest.post(
            "/api/projects",
            json={"name": "Second guest", "description": "Second guest only"},
        )
        assert second_project.status_code == 201

    first_guest_projects = client.get("/api/projects").json()
    assert {project["name"] for project in first_guest_projects} == {
        "Photography workshop",
        "First guest project",
    }
