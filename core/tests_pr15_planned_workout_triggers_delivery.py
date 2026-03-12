"""
PR15 Tests: trigger_workout_delivery_if_applicable

Coverage:
  a) Coach create enqueues when provider declared capable + athlete connected
  b) Strava-only does NOT enqueue (no outbound_workouts cap)
  c) No connected providers → zero calls
  d) Athlete update does NOT enqueue
  e) aplicar_a_equipo enqueues N times (one per eligible athlete)
  f) organization_id passed = alumno.entrenador_id

Patch targets:
  - integrations.outbound.workout_delivery.queue_workout_delivery  (PR14 delivery function)
      Patched at source because core/services.py uses a lazy import (Law 4, PR-127).
  - core.services.provider_supports        (PR13 capability gate)
    → patched in positive-path tests (a/e/f) because no provider currently
      declares CAP_OUTBOUND_WORKOUTS in PROVIDER_CAPABILITIES; patching
      simulates a future garmin capable device without modifying PR13.

Real OAuthCredential rows are used to test the PR11 connection gate.
"""
import pytest
from unittest.mock import patch, call

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Alumno, Entrenamiento, OAuthCredential, Equipo, PlantillaEntrenamiento
from core.provider_capabilities import CAP_OUTBOUND_WORKOUTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _jwt(user: User) -> str:
    return str(RefreshToken.for_user(user).access_token)


def _make_coach(username: str) -> User:
    return User.objects.create_user(username=username, password="x")


def _make_athlete_user(username: str) -> User:
    return User.objects.create_user(username=username, password="x")


def _make_alumno(coach: User, athlete_user: User = None, *, suffix: str = "") -> Alumno:
    return Alumno.objects.create(
        entrenador=coach,
        usuario=athlete_user,
        nombre=f"PR15{suffix}",
        apellido="Tester",
    )


def _make_entrenamiento(alumno: Alumno, *, fecha: str = "2026-03-01") -> Entrenamiento:
    return Entrenamiento.objects.create(
        alumno=alumno,
        titulo="Test WO PR15",
        fecha_asignada=fecha,
        tipo_actividad="RUN",
        completado=False,
    )


def _connect_garmin(alumno: Alumno) -> OAuthCredential:
    """Create a valid (non-expired) OAuthCredential for garmin."""
    return OAuthCredential.objects.create(
        alumno=alumno,
        provider="garmin",
        external_user_id=f"garmin-uid-{alumno.pk}",
        access_token=f"tok-garmin-{alumno.pk}",
        expires_at=timezone.now() + timezone.timedelta(hours=2),
    )


def _provider_supports_garmin(provider: str, capability: str) -> bool:
    """
    Stub for provider_supports that treats garmin as outbound-capable.
    Used in positive-path tests only.
    No provider currently declares CAP_OUTBOUND_WORKOUTS in PROVIDER_CAPABILITIES
    (PR13 is additive and garmin will be listed once the device SDK is integrated).
    """
    if provider == "garmin" and capability == CAP_OUTBOUND_WORKOUTS:
        return True
    return False


# ---------------------------------------------------------------------------
# a) Coach create enqueues for eligible provider
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_coach_create_enqueues_for_eligible_provider():
    """
    GIVEN: garmin mocked as outbound-capable + athlete has garmin connected.
    WHEN:  trigger_workout_delivery_if_applicable is called.
    THEN:  queue_workout_delivery is called exactly once with correct kwargs.
    """
    from core.services import trigger_workout_delivery_if_applicable

    coach = _make_coach("pr15_coach_a")
    alumno = _make_alumno(coach, suffix="_a")
    _connect_garmin(alumno)
    entrenamiento = _make_entrenamiento(alumno)

    with patch("integrations.outbound.workout_delivery.queue_workout_delivery") as mock_q, \
         patch("core.services.provider_supports", side_effect=_provider_supports_garmin):
        trigger_workout_delivery_if_applicable(entrenamiento, actor_user=coach)

    mock_q.assert_called_once_with(
        organization_id=coach.id,
        athlete_id=alumno.id,
        provider="garmin",
        planned_workout_id=entrenamiento.id,
        payload={},
    )


# ---------------------------------------------------------------------------
# b) Strava-only does NOT enqueue (natural — no outbound cap)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_strava_only_does_not_enqueue():
    """
    GIVEN: Strava has no outbound_workouts capability (PR13 default).
    WHEN:  trigger is called with no other providers connected.
    THEN:  queue_workout_delivery is NEVER called (Strava blocked at cap gate).
    No mocking of provider_supports — Strava natural state must block it.
    """
    from core.services import trigger_workout_delivery_if_applicable

    coach = _make_coach("pr15_coach_b")
    alumno = _make_alumno(coach, suffix="_b")
    entrenamiento = _make_entrenamiento(alumno)

    with patch("integrations.outbound.workout_delivery.queue_workout_delivery") as mock_q:
        trigger_workout_delivery_if_applicable(entrenamiento, actor_user=coach)

    mock_q.assert_not_called()


# ---------------------------------------------------------------------------
# c) No connected providers → zero calls
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_no_connected_providers_does_not_enqueue():
    """
    GIVEN: garmin mocked as outbound-capable BUT athlete has no OAuthCredential.
    WHEN:  trigger is called.
    THEN:  queue_workout_delivery is NEVER called (connection gate blocks it).
    """
    from core.services import trigger_workout_delivery_if_applicable

    coach = _make_coach("pr15_coach_c")
    alumno = _make_alumno(coach, suffix="_c")
    entrenamiento = _make_entrenamiento(alumno)
    # No OAuthCredential created → compute_connection_status returns "disconnected"

    with patch("integrations.outbound.workout_delivery.queue_workout_delivery") as mock_q, \
         patch("core.services.provider_supports", side_effect=_provider_supports_garmin):
        trigger_workout_delivery_if_applicable(entrenamiento, actor_user=coach)

    mock_q.assert_not_called()


# ---------------------------------------------------------------------------
# d) Athlete update does NOT enqueue
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_athlete_update_does_not_enqueue(client):
    """
    GIVEN: Athlete PATCHes their own workout via /api/entrenamientos/{id}/.
    WHEN:  perform_update is called as athlete (is_owner_athlete=True, is_coach_owner=False).
    THEN:  queue_workout_delivery is NEVER called.

    The views.py guard: trigger fires only when is_coach_owner=True.
    """
    coach = _make_coach("pr15_coach_d")
    athlete_user = _make_athlete_user("pr15_athlete_d")
    alumno = _make_alumno(coach, athlete_user, suffix="_d")
    _connect_garmin(alumno)
    entrenamiento = _make_entrenamiento(alumno)

    endpoint = f"/api/entrenamientos/{entrenamiento.id}/"

    with patch("integrations.outbound.workout_delivery.queue_workout_delivery") as mock_q, \
         patch("core.services.provider_supports", side_effect=_provider_supports_garmin):
        response = client.patch(
            endpoint,
            {"rpe": 7},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {_jwt(athlete_user)}",
        )

    # Regardless of HTTP response code, trigger must NOT have fired for athlete
    mock_q.assert_not_called()


# ---------------------------------------------------------------------------
# e) aplicar_a_equipo enqueues N times
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_aplicar_a_equipo_enqueues_per_eligible_athlete(client):
    """
    GIVEN: equipo with 2 athletes, each with garmin connected (mocked capable).
    WHEN:  POST /api/plantillas/{id}/aplicar_a_equipo/ is called by coach.
    THEN:  queue_workout_delivery is called 2 times (one per athlete).
    """
    coach = _make_coach("pr15_coach_e")

    athlete1 = _make_athlete_user("pr15_ath_e1")
    athlete2 = _make_athlete_user("pr15_ath_e2")
    alumno1 = _make_alumno(coach, athlete1, suffix="_e1")
    alumno2 = _make_alumno(coach, athlete2, suffix="_e2")

    equipo = Equipo.objects.create(entrenador=coach, nombre="Team PR15")
    equipo.alumnos.set([alumno1, alumno2])

    plantilla = PlantillaEntrenamiento.objects.create(
        entrenador=coach,
        titulo="Plantilla PR15",
        deporte="RUN",
        estructura={},
    )

    _connect_garmin(alumno1)
    _connect_garmin(alumno2)

    with patch("integrations.outbound.workout_delivery.queue_workout_delivery") as mock_q, \
         patch("core.services.provider_supports", side_effect=_provider_supports_garmin):
        response = client.post(
            f"/api/plantillas/{plantilla.id}/aplicar_a_equipo/",
            {"equipo_id": equipo.id, "fecha_inicio": "2026-04-01"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {_jwt(coach)}",
        )

    assert response.status_code == 201, response.content
    assert mock_q.call_count == 2


# ---------------------------------------------------------------------------
# f) organization_id = alumno.entrenador_id
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_organization_id_is_coach_id():
    """
    GIVEN: garmin mocked capable + athlete connected.
    WHEN:  trigger is called.
    THEN:  queue_workout_delivery receives organization_id = coach.id = alumno.entrenador_id.
    """
    from core.services import trigger_workout_delivery_if_applicable

    coach = _make_coach("pr15_coach_f")
    alumno = _make_alumno(coach, suffix="_f")
    _connect_garmin(alumno)
    entrenamiento = _make_entrenamiento(alumno)

    with patch("integrations.outbound.workout_delivery.queue_workout_delivery") as mock_q, \
         patch("core.services.provider_supports", side_effect=_provider_supports_garmin):
        trigger_workout_delivery_if_applicable(entrenamiento, actor_user=coach)

    assert mock_q.call_count == 1
    kwargs = mock_q.call_args.kwargs
    assert kwargs["organization_id"] == coach.id
    assert kwargs["organization_id"] == alumno.entrenador_id
