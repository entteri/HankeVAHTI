import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    Evaluation,
    EvaluationStatus,
    FundingCall,
    Participation,
    ParticipationStage,
    SearchProfile,
)


def test_models_save_and_load(db_session):
    call = FundingCall(source="EURA", source_id="123", title="Oppimishanke", raw_data={"id": 123})
    call.evaluation = Evaluation(status=EvaluationStatus.NEW)
    call.participation = Participation(stage=ParticipationStage.NOT_STARTED)
    profile = SearchProfile(name="Oppiminen", keywords=["koulutus"], excluded_keywords=[])
    db_session.add_all([call, profile])
    db_session.commit()
    db_session.expire_all()

    loaded = db_session.get(FundingCall, call.id)
    assert loaded.source_id == "123"
    assert loaded.raw_data == {"id": 123}
    assert loaded.evaluation.status is EvaluationStatus.NEW
    assert loaded.participation.stage is ParticipationStage.NOT_STARTED
    assert db_session.get(SearchProfile, profile.id).active is True


def test_source_and_source_id_are_unique_together(db_session):
    db_session.add_all([
        FundingCall(source="EURA", source_id="123", title="Ensimmäinen"),
        FundingCall(source="EURA", source_id="123", title="Toinen"),
    ])
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_same_source_id_from_different_sources_is_allowed(db_session):
    db_session.add_all([
        FundingCall(source="EURA", source_id="123", title="EURA-hanke"),
        FundingCall(source="HAEAVUSTUKSIA", source_id="123", title="Muu hanke"),
    ])
    db_session.commit()


def test_evaluation_score_must_be_in_range(db_session):
    call = FundingCall(source="EURA", source_id="123", title="Hanke")
    call.evaluation = Evaluation(suitability_score=101)
    db_session.add(call)
    with pytest.raises(IntegrityError):
        db_session.commit()
