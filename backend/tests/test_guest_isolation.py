from fastapi.testclient import TestClient

from app.main import app


def test_guest_entry_and_workspace_isolation(client: TestClient) -> None:
    assert client.get("/api/guest-session").json() == {"active": False}
    assert client.post("/api/guest-session").json() == {"active": True}
    assert client.get("/api/guest-session").json() == {"active": True}

    first_project = client.post(
        "/api/projects",
        json={"name": "Recruiter demo", "description": "First guest only"},
    )
    assert first_project.status_code == 201

    with TestClient(app) as second_guest:
        assert second_guest.post("/api/guest-session").status_code == 200
        assert second_guest.get("/api/projects").json() == []
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
    assert [project["name"] for project in first_guest_projects] == ["Recruiter demo"]
