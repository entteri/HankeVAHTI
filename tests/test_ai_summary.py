import json

import httpx
import pytest
from sqlalchemy import select

from app.models import Evaluation, EvaluationStatus, FundingCall
from app.services.ai_summary import OPENAI_RESPONSES_URL, SummaryError, generate_ai_summary


def _selected_call(session):
    call = FundingCall(
        source="EURA",
        source_id="test-1",
        title="Digitaalisen oppimisen hanke",
        description="Hanke kehittää henkilöstön digitaitoja.",
        fund="ESR+",
        evaluation=Evaluation(status=EvaluationStatus.PARTICIPATE, suitability_summary="Oma arvio"),
    )
    session.add(call)
    session.commit()
    return call


def test_ai_summary_uses_current_files_and_preserves_manual_evaluation(db_session, tmp_path, monkeypatch):
    call = _selected_call(db_session)
    profile = tmp_path / "asiakas.md"
    criteria = tmp_path / "arviointikriteerit.md"
    profile.write_text("Asiakas kouluttaa henkilöstöä digitaidoissa.", encoding="utf-8")
    criteria.write_text("Vertaa asiakkaan osaamista hankkeen tavoitteisiin.", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setattr("app.services.ai_summary.PROJECT_ROOT", tmp_path)

    def handler(request):
        assert str(request.url) == OPENAI_RESPONSES_URL
        assert request.headers["Authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert payload["store"] is False
        assert "Asiakas kouluttaa henkilöstöä digitaidoissa." in payload["input"]
        assert "Vertaa asiakkaan osaamista hankkeen tavoitteisiin." in payload["input"]
        assert "Hanke kehittää henkilöstön digitaitoja." in payload["input"]
        return httpx.Response(200, json={
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "Hanke sopii digitaitoihin. Rahoituskelpoisuus on selvitettävä."}]}],
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        summary = generate_ai_summary(db_session, call.id, client=client)

    db_session.expire_all()
    saved = db_session.scalar(select(FundingCall).where(FundingCall.id == call.id))
    assert summary == saved.evaluation.ai_summary
    assert saved.evaluation.suitability_summary == "Oma arvio"
    assert saved.evaluation.status is EvaluationStatus.PARTICIPATE


def test_ai_summary_requires_profile_and_selected_call(db_session, tmp_path, monkeypatch):
    call = _selected_call(db_session)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with pytest.raises(SummaryError, match="asiakas.md puuttuu"):
        generate_ai_summary(db_session, call.id, profile_path=tmp_path / "asiakas.md")

    call.evaluation.status = EvaluationStatus.REJECTED
    db_session.commit()
    with pytest.raises(SummaryError, match="valituista hankkeista"):
        generate_ai_summary(db_session, call.id)


def test_ai_summary_failure_keeps_previous_summary(db_session, tmp_path, monkeypatch):
    call = _selected_call(db_session)
    call.evaluation.ai_summary = "Aiempi yhteenveto"
    db_session.commit()
    profile = tmp_path / "asiakas.md"
    criteria = tmp_path / "arviokriteerit.md"
    profile.write_text("Asiakas", encoding="utf-8")
    criteria.write_text("Kriteerit", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client:
        with pytest.raises(SummaryError, match="Tekoälypalveluun"):
            generate_ai_summary(db_session, call.id, client=client, profile_path=profile, criteria_path=criteria)

    db_session.refresh(call.evaluation)
    assert call.evaluation.ai_summary == "Aiempi yhteenveto"
