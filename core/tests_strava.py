import json
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from celery.exceptions import Retry
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from analytics.models import SessionComparison
from core.models import (
    Alumno,
    Entrenamiento,
    Actividad,
    StravaWebhookEvent,
    StravaImportLog,
    StravaActivitySyncState,
)
from core.tasks import process_strava_event
from core.strava_mapper import map_strava_raw_activity_to_actividad_defaults


User = get_user_model()


class StravaRawJsonMapperTests(TestCase):
    def test_map_raw_json_maps_required_fields_safely(self):
        raw = {
            "id": 123456,
            "name": "Test Run",
            "distance": 5000.0,
            "moving_time": 1500,
            "elapsed_time": 1550,
            "start_date": "2025-12-19T10:00:00Z",
            "sport_type": "Run",
            "total_elevation_gain": 42.5,
            "map": {"summary_polyline": "xyz"},
        }

        mapped = map_strava_raw_activity_to_actividad_defaults(raw)

        self.assertEqual(mapped["source"], "strava")
        self.assertEqual(mapped["source_object_id"], "123456")
        self.assertEqual(mapped["strava_id"], 123456)
        self.assertEqual(mapped["nombre"], "Test Run")
        self.assertEqual(mapped["tipo_deporte"], "Run")
        self.assertEqual(mapped["distancia"], 5000.0)
        self.assertEqual(mapped["tiempo_movimiento"], 1500)
        self.assertEqual(mapped["desnivel_positivo"], 42.5)
        self.assertEqual(mapped["mapa_polilinea"], "xyz")
        self.assertTrue(mapped["source_hash"])
        # fecha_inicio parseada (datetime aware o naive aceptable por el modelo)
        self.assertIsNotNone(mapped["fecha_inicio"])


class _FakeAthlete:
    def __init__(self, athlete_id: int):
        self.id = athlete_id


class _FakeMap:
    def __init__(self, poly: str | None = None):
        self.summary_polyline = poly


class _FakeStravaActivity:
    def __init__(
        self,
        *,
        activity_id: int,
        athlete_id: int,
        name: str,
        type_: str,
        start: datetime,
        distance_m: float,
        moving_time_s: int,
        elapsed_time_s: int | None = None,
        elev_m: float = 0.0,
        polyline: str | None = "abc",
    ):
        self.id = activity_id
        self.athlete = _FakeAthlete(athlete_id)
        self.name = name
        self.type = type_
        self.start_date_local = start
        self.start_date = start
        self.distance = distance_m
        self.moving_time = moving_time_s
        self.elapsed_time = elapsed_time_s if elapsed_time_s is not None else moving_time_s
        self.total_elevation_gain = elev_m
        self.map = _FakeMap(polyline)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "distance": self.distance,
            "moving_time": self.moving_time,
            "elapsed_time": self.elapsed_time,
        }


class _FakeStravaClient:
    def __init__(self, activity: _FakeStravaActivity):
        self._activity = activity

    def get_activity(self, activity_id: int):
        assert int(activity_id) == int(self._activity.id)
        return self._activity


class StravaWebhookThinEndpointTests(TestCase):
    def test_webhook_idempotency_same_payload_twice_creates_one_event(self):
        payload = {
            "object_type": "activity",
            "aspect_type": "create",
            "object_id": 123,
            "owner_id": 999,
            "subscription_id": 1,
            "event_time": 1700000000,
        }

        with patch("core.webhooks.process_strava_event.delay") as delay_mock:
            res1 = self.client.post(
                "/webhooks/strava/",
                data=json.dumps(payload),
                content_type="application/json",
            )
            res2 = self.client.post(
                "/webhooks/strava/",
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(StravaWebhookEvent.objects.count(), 1)
        self.assertEqual(delay_mock.call_count, 1)

    def test_webhook_discard_non_activity_does_not_enqueue(self):
        payload = {
            "object_type": "athlete",
            "aspect_type": "update",
            "object_id": 123,
            "owner_id": 999,
            "subscription_id": 1,
            "event_time": 1700000001,
        }
        with patch("core.webhooks.process_strava_event.delay") as delay_mock:
            res = self.client.post(
                "/webhooks/strava/",
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(res.status_code, 200)
        self.assertEqual(delay_mock.call_count, 0)
        self.assertEqual(StravaWebhookEvent.objects.count(), 1)
        ev = StravaWebhookEvent.objects.first()
        self.assertEqual(ev.status, StravaWebhookEvent.Status.DISCARDED)
        self.assertEqual(ev.discard_reason, "non_activity_event")


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class StravaIngestionRobustTests(TestCase):
    def setUp(self):
        self.coach1 = User.objects.create_user(username="coach1_strava", password="x")
        self.coach2 = User.objects.create_user(username="coach2_strava", password="x")

        self.alumno1 = Alumno.objects.create(
            entrenador=self.coach1,
            nombre="Ana",
            apellido="A",
            email="ana_strava@test.com",
            strava_athlete_id="111",
        )
        self.alumno2 = Alumno.objects.create(
            entrenador=self.coach2,
            nombre="Beto",
            apellido="B",
            email="beto_strava@test.com",
            strava_athlete_id="222",
        )

    def _mk_event(self, *, uid: str, owner_id: int, object_id: int, aspect: str = "create"):
        return StravaWebhookEvent.objects.create(
            event_uid=uid,
            object_type="activity",
            object_id=object_id,
            aspect_type=aspect,
            owner_id=owner_id,
            subscription_id=1,
            payload_raw={"test": True},
            status=StravaWebhookEvent.Status.QUEUED,
        )

    def test_activity_dedupe_same_strava_id_update_not_create(self):
        start = datetime.now(dt_timezone.utc)
        a1 = _FakeStravaActivity(
            activity_id=555,
            athlete_id=111,
            name="Morning Run",
            type_="Run",
            start=start,
            distance_m=10000,
            moving_time_s=3600,
            elev_m=120,
        )
        a2 = _FakeStravaActivity(
            activity_id=555,
            athlete_id=111,
            name="Morning Run (edited)",
            type_="Run",
            start=start,
            distance_m=11000,
            moving_time_s=3700,
            elev_m=140,
        )

        e1 = self._mk_event(uid="e1", owner_id=111, object_id=555, aspect="create")
        with patch("core.services.obtener_cliente_strava", return_value=_FakeStravaClient(a1)):
            process_strava_event.delay(e1.id)

        self.assertEqual(Actividad.objects.count(), 1)
        self.assertEqual(Entrenamiento.objects.filter(strava_id="555").count(), 1)

        e2 = self._mk_event(uid="e2", owner_id=111, object_id=555, aspect="update")
        with patch("core.services.obtener_cliente_strava", return_value=_FakeStravaClient(a2)):
            process_strava_event.delay(e2.id)

        self.assertEqual(Actividad.objects.count(), 1)
        act = Actividad.objects.get(strava_id=555)
        self.assertEqual(act.nombre, "Morning Run (edited)")
        self.assertEqual(Entrenamiento.objects.filter(strava_id="555").count(), 1)
        self.assertEqual(SessionComparison.objects.filter(activity=act).count(), 1)

    def test_raw_json_datetime_is_sanitized_before_saving(self):
        """
        Repro del bug: Strava raw payload puede traer datetime (ej: start_date).
        Debe persistirse en JSONField como string ISO sin explotar.
        """
        start = datetime.now(dt_timezone.utc)
        a = _FakeStravaActivity(
            activity_id=556,
            athlete_id=111,
            name="Datetime Raw Run",
            type_="Run",
            start=start,
            distance_m=5000,
            moving_time_s=1500,
        )
        original_to_dict = a.to_dict

        def _to_dict_with_datetime():
            d = original_to_dict()
            d["start_date"] = start
            return d

        a.to_dict = _to_dict_with_datetime  # type: ignore[method-assign]

        e = self._mk_event(uid="e_raw_datetime", owner_id=111, object_id=556, aspect="create")
        with patch("core.services.obtener_cliente_strava", return_value=_FakeStravaClient(a)):
            process_strava_event.delay(e.id)

        act = Actividad.objects.get(strava_id=556)
        self.assertIsInstance(act.datos_brutos.get("start_date"), str)
        self.assertEqual(act.datos_brutos.get("start_date"), start.isoformat())

    def test_unknown_athlete_is_deferred_link_required(self):
        e = self._mk_event(uid="e_unknown", owner_id=999999, object_id=12345, aspect="create")
        # No hay alumno con strava_athlete_id=999999
        process_strava_event.delay(e.id)
        e.refresh_from_db()
        self.assertEqual(e.status, StravaWebhookEvent.Status.LINK_REQUIRED)
        self.assertEqual(e.discard_reason, "link_required")
        self.assertTrue(
            StravaImportLog.objects.filter(event=e, status=StravaImportLog.Status.DEFERRED, reason="link_required").exists()
        )
        # Lock state queda BLOCKED para permitir re-procesar al linkear (no se "quema" como discarded).
        state = StravaActivitySyncState.objects.get(provider="strava", strava_activity_id=12345)
        self.assertEqual(state.status, StravaActivitySyncState.Status.BLOCKED)
        self.assertEqual(state.discard_reason, "link_required")

    def test_missing_auth_fails_with_discard_reason_and_message(self):
        start = datetime.now(dt_timezone.utc)
        e = self._mk_event(uid="e_noauth", owner_id=111, object_id=901, aspect="create")

        # No hay SocialToken en tests, por lo que debe fallar antes de fetch.
        # Patch por seguridad: aunque exista un cliente, el pipeline debe cortar por missing auth.
        with patch("core.services.obtener_cliente_strava_para_alumno", return_value=None):
            process_strava_event.delay(e.id)

        e.refresh_from_db()
        self.assertEqual(e.status, StravaWebhookEvent.Status.FAILED)
        self.assertEqual(e.discard_reason, "missing_strava_auth")
        self.assertTrue(e.error_message)
        self.assertTrue(
            StravaImportLog.objects.filter(event=e, status=StravaImportLog.Status.FAILED, reason="missing_strava_auth").exists()
        )

    def test_discard_rules_invalid_activity_is_discarded(self):
        start = datetime.now(dt_timezone.utc)
        ride = _FakeStravaActivity(
            activity_id=777,
            athlete_id=111,
            name="Bike Ride",
            type_="Ride",
            start=start,
            distance_m=20000,
            moving_time_s=3600,
        )
        e = self._mk_event(uid="e_discard", owner_id=111, object_id=777, aspect="create")

        with patch("core.services.obtener_cliente_strava", return_value=_FakeStravaClient(ride)):
            process_strava_event.delay(e.id)

        act = Actividad.objects.get(strava_id=777)
        self.assertEqual(act.validity, Actividad.Validity.DISCARDED)
        self.assertEqual(act.invalid_reason, "unsupported_type")
        self.assertEqual(Entrenamiento.objects.filter(strava_id="777").count(), 0)
        self.assertTrue(
            StravaImportLog.objects.filter(event=e, status=StravaImportLog.Status.DISCARDED).exists()
        )

    def test_retry_on_rate_limit_429_raises_retry_and_marks_queued(self):
        e = self._mk_event(uid="e_429", owner_id=111, object_id=999, aspect="create")

        class _RateLimitClient:
            def get_activity(self, _activity_id: int):
                raise Exception("429 rate limit")

        with patch("core.services.obtener_cliente_strava", return_value=_RateLimitClient()):
            with self.assertRaises(Retry):
                process_strava_event.delay(e.id)

        e.refresh_from_db()
        self.assertEqual(e.status, StravaWebhookEvent.Status.QUEUED)
        self.assertIn("rate_limit", (e.last_error or "").lower())
        self.assertTrue(
            StravaImportLog.objects.filter(event=e, status=StravaImportLog.Status.FAILED, reason="rate_limit").exists()
        )
        # Lock lógico debe existir (se mantiene RUNNING mientras reintenta)
        state = StravaActivitySyncState.objects.get(provider="strava", strava_activity_id=999)
        self.assertEqual(state.status, StravaActivitySyncState.Status.RUNNING)
        self.assertEqual(state.locked_by_event_uid, e.event_uid)

    def test_multi_tenant_processing_scoped_by_athlete_id(self):
        start = datetime.now(dt_timezone.utc)
        a = _FakeStravaActivity(
            activity_id=888,
            athlete_id=222,
            name="Beto Run",
            type_="Run",
            start=start,
            distance_m=5000,
            moving_time_s=1500,
        )
        e = self._mk_event(uid="e_tenant", owner_id=222, object_id=888, aspect="create")

        with patch("core.services.obtener_cliente_strava", return_value=_FakeStravaClient(a)):
            process_strava_event.delay(e.id)

        # Solo afecta a alumno2 (coach2)
        self.assertEqual(Entrenamiento.objects.filter(alumno=self.alumno1).count(), 0)
        self.assertEqual(Entrenamiento.objects.filter(alumno=self.alumno2, strava_id="888").count(), 1)
        act = Actividad.objects.get(strava_id=888)
        self.assertEqual(act.alumno_id, self.alumno2.id)
        comp = SessionComparison.objects.get(activity=act)
        self.assertEqual(comp.entrenador_id, self.coach2.id)


class PlannedVsActualComparatorTests(TestCase):
    def setUp(self):
        self.coach = User.objects.create_user(username="coach_cmp", password="x")
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Ana",
            apellido="Cmp",
            email="ana_cmp@test.com",
        )

    def _mk_activity(self, *, strava_id: int, distance_m: float, moving_s: int):
        return Actividad.objects.create(
            usuario=self.coach,
            alumno=self.alumno,
            strava_id=strava_id,
            nombre="Act",
            distancia=distance_m,
            tiempo_movimiento=moving_s,
            fecha_inicio=timezone.now(),
            tipo_deporte="Run",
            desnivel_positivo=0.0,
        )

    def test_comparator_on_track(self):
        from analytics.plan_vs_actual import PlannedVsActualComparator

        planned = Entrenamiento.objects.create(
            alumno=self.alumno,
            fecha_asignada=timezone.localdate(),
            titulo="Plan",
            tipo_actividad="RUN",
            distancia_planificada_km=10,
            tiempo_planificado_min=60,
            completado=False,
        )
        act = self._mk_activity(strava_id=1, distance_m=10000, moving_s=3600)
        res = PlannedVsActualComparator().compare(planned, act)
        self.assertEqual(res.classification, "on_track")

    def test_comparator_under(self):
        from analytics.plan_vs_actual import PlannedVsActualComparator

        planned = Entrenamiento.objects.create(
            alumno=self.alumno,
            fecha_asignada=timezone.localdate(),
            titulo="Plan",
            tipo_actividad="RUN",
            distancia_planificada_km=10,
            tiempo_planificado_min=60,
            completado=False,
        )
        act = self._mk_activity(strava_id=2, distance_m=5000, moving_s=1800)
        res = PlannedVsActualComparator().compare(planned, act)
        self.assertEqual(res.classification, "under")

    def test_comparator_over(self):
        from analytics.plan_vs_actual import PlannedVsActualComparator

        planned = Entrenamiento.objects.create(
            alumno=self.alumno,
            fecha_asignada=timezone.localdate(),
            titulo="Plan",
            tipo_actividad="RUN",
            distancia_planificada_km=10,
            tiempo_planificado_min=60,
            completado=False,
        )
        act = self._mk_activity(strava_id=3, distance_m=16000, moving_s=5400)
        res = PlannedVsActualComparator().compare(planned, act)
        self.assertEqual(res.classification, "over")
