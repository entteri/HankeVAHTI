from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_dashboard_renders_placeholders():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    for text in (
        "HankeVAHTI",
        "Hae uudet hankkeet",
        "Hakuehdot",
        "Asetukset",
        "Uusia hankkeita",
        "Arvioimattomia hankkeita",
        "Osallistuttavia hankkeita",
        "Hylättyjä hankkeita",
        "Käynnissä olevia hankkeita",
    ):
        assert text in response.text
