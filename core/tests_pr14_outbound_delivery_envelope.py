import pytest
from integrations.outbound.workout_delivery import queue_workout_delivery

pytestmark = pytest.mark.django_db

def test_unknown_provider_is_fail_closed():
    result = queue_workout_delivery(
        organization_id=1,
        athlete_id=1,
        provider="unknown",
        planned_workout_id=1,
        payload={"dummy": "data"}
    )
    
    assert result["status"] == "skipped"
    assert result["reason_code"] == "provider_unknown"

def test_provider_without_outbound_is_skipped():
    result = queue_workout_delivery(
        organization_id=1,
        athlete_id=1,
        provider="strava",
        planned_workout_id=1,
        payload={"dummy": "data"}
    )
    
    assert result["status"] == "skipped"
    assert result["reason_code"] == "provider_no_outbound"

def test_missing_required_fields_returns_error(monkeypatch):
    monkeypatch.setattr("integrations.outbound.workout_delivery.provider_supports", lambda p, c: True)

    result_no_payload = queue_workout_delivery(
        organization_id=1,
        athlete_id=1,
        provider="garmin",
        planned_workout_id=1,
        payload={}
    )
    
    assert result_no_payload["status"] == "error"
    assert result_no_payload["reason_code"] == "missing_required"

    result_no_org = queue_workout_delivery(
        organization_id=0,
        athlete_id=1,
        provider="garmin",
        planned_workout_id=1,
        payload={"dummy": "data"}
    )
    
    assert result_no_org["status"] == "error"
    assert result_no_org["reason_code"] == "missing_required"

def test_valid_delivery_is_queued(monkeypatch):
    # Monkeypatch to force capability
    monkeypatch.setattr("integrations.outbound.workout_delivery.provider_supports", lambda p, c: True)
    
    result = queue_workout_delivery(
        organization_id=1,
        athlete_id=1,
        provider="garmin",
        planned_workout_id=1,
        payload={"dummy": "data"}
    )
    
    assert result["status"] == "queued"
    assert result["reason_code"] == "queued"
