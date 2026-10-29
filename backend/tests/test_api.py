"""The API's routes that need no model, through FastAPI's TestClient."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    settings = Settings(openrouter_api_key="test", firecrawl_api_key="test", data_dir=tmp_path)
    with TestClient(create_app(settings)) as client:  # `with` runs the lifespan: the memory opens
        yield client


@pytest.fixture
def brand_id(client):
    return client.post("/brands").json()["brand_id"]


def test_a_new_brand_has_an_empty_design_system(client, brand_id):
    response = client.get(f"/brands/{brand_id}")
    assert response.status_code == 200
    assert response.json()["colors"] == []


def test_an_unknown_brand_is_404(client):
    assert client.get("/brands/deadbeef").status_code == 404
    assert client.post("/brands/deadbeef/sessions").status_code == 404


def test_uploaded_files_are_saved_and_served(client, brand_id):
    response = client.post(f"/brands/{brand_id}/uploads", files=[("files", ("logo.png", b"fake png", "image/png"))])
    assert response.json() == {"files": ["logo.png"]}

    served = client.get(f"/brands/{brand_id}/files/uploads/logo.png")
    assert served.status_code == 200
    assert served.content == b"fake png"
    assert client.get(f"/brands/{brand_id}/files/uploads/nope.png").status_code == 404
    assert client.get(f"/brands/{brand_id}/files/raw/page.html").status_code == 422  # only assets and uploads


def test_a_field_can_be_corrected(client, brand_id):
    response = client.patch(f"/brands/{brand_id}", json={"field": "identity.language", "value": "it"})
    assert response.json()["identity"]["language"] == "it"
    assert client.patch(f"/brands/{brand_id}", json={"field": "nope", "value": 1}).status_code == 422


def test_a_new_session_has_no_email_yet(client, brand_id):
    session_id = client.post(f"/brands/{brand_id}/sessions").json()["session_id"]

    response = client.get(f"/brands/{brand_id}/sessions/{session_id}/email")

    assert response.json()["email"] == {"sections": []}
    assert "<!DOCTYPE html>" in response.json()["html"]
