from fastapi.testclient import TestClient

from app.main import create_app


def make_client(tmp_path):
    app = create_app(database_path=tmp_path / "test.sqlite3", start_scheduler=False)
    return TestClient(app)


def test_create_child(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/children",
            json={"name": "小明", "qq_number": "123456"},
        )

    assert response.status_code == 201
    assert response.json()["name"] == "小明"
    assert response.json()["qq_number"] == "123456"


def test_create_child_rejects_invalid_qq(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(
            "/api/children",
            json={"name": "小明", "qq_number": "abc"},
        )

    assert response.status_code == 422


def test_list_children_includes_assignment_count(tmp_path):
    with make_client(tmp_path) as client:
        client.post(
            "/api/children",
            json={"name": "小明", "qq_number": "123456"},
        )
        response = client.get("/api/children")

    assert response.status_code == 200
    assert response.json()[0]["assignment_count"] == 0


def test_update_child(tmp_path):
    with make_client(tmp_path) as client:
        create_response = client.post(
            "/api/children",
            json={"name": "小明", "qq_number": "123456"},
        )
        child_id = create_response.json()["id"]

        response = client.patch(
            f"/api/children/{child_id}",
            json={"name": "小红", "qq_number": "654321"},
        )

    assert response.status_code == 200
    assert response.json()["name"] == "小红"
    assert response.json()["qq_number"] == "654321"
