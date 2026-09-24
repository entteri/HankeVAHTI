from fastapi.testclient import TestClient

from app.main import app
from app.ui.dashboard import _import_feedback


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_dashboard_renders_navigation_and_metrics():
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 200
    for text in (
        "HankeVAHTI",
        "Hae uudet hankkeet",
        "Kaikki hankkeet",
        "Arvioi hankkeita",
        "Hakuehdot",
        "Asetukset",
        "Uusia hankkeita",
        "Arvioimattomia hankkeita",
        "Osallistuttavia hankkeita",
        "Hylättyjä hankkeita",
        "Käynnissä olevia hankkeita",
    ):
        assert text in response.text


def test_import_endpoint_returns_counts(monkeypatch):
    expected = {
        "eura": {"created": 1, "updated": 0, "unchanged": 0},
        "haeavustuksia": {"created": 2, "updated": 0, "unchanged": 0},
    }
    monkeypatch.setattr("app.api.imports.run_imports", lambda db: expected)
    with TestClient(app) as client:
        response = client.post("/api/imports/run")
    assert response.status_code == 200
    assert response.json() == expected


def test_import_endpoint_reports_upstream_failure(monkeypatch):
    def fail(db):
        raise ValueError("Virheellinen lähdedata")

    monkeypatch.setattr("app.api.imports.run_imports", fail)
    with TestClient(app) as client:
        response = client.post("/api/imports/run")
    assert response.status_code == 502
    assert response.json() == {"detail": "Tietolähteiden tuonti epäonnistui"}


def test_import_feedback_says_when_no_new_calls_were_found():
    result = {
        "eura": {"created": 0, "updated": 1, "unchanged": 2},
        "haeavustuksia": {"created": 0, "updated": 0, "unchanged": 10},
    }
    assert _import_feedback(result) == ("Uusia hankkeita ei löytynyt. Päivitettyjä: 1.", "info")
