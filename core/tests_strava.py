import json
import logging
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
from core.tasks import process_strava_event, _build_strava_activity_upserted_extra, _log_strava_activity_upserted
from core.services import LegacyStravaSyncDisabled, sincronizar_actividades_strava
from core.utils.logging import RESERVED_LOGRECORD_ATTRS


User = get_user_model()


class StravaSportTypeMappingTests(TestCase):
    def test_normalizer_prefers_nested_raw_sport_type_and_maps_trailrun(self):
        """
        Regresión: el pipeline pasa a veces sport_type dentro de `raw`.
        No debe terminar como OTHER si es TrailRun/Run/Ride.
        """
        from core.strava_activity_normalizer import normalize_strava_activity_payload

        payload = {
            # legacy type puede venir ruidoso; debe preferir raw.sport_type
            "type": "Other",
            "raw": {"sport_type": "TrailRun"},
            "distance_m": 1234,
            "moving_time_s": 600,
            "start_date_local": timezone.now(),
        }
        normalized = normalize_strava_activity_payload(payload)
        self.assertEqual(normalized["tipo_deporte"], "TRAIL")
        self.assertEqual(normalized["strava_sport_type"], "TRAILRUN")

    def test_sport_type_normalization_mapping_virtualride_to_bike(self):
        from core.strava_activity_normalizer import normalize_strava_activity_payload

        payload = {
            "sport_type": "VirtualRide",
            "distance_m": 1234,
            "moving_time_s": 600,
            "start_date_local": timezone.now(),
        }
        normalized = normalize_strava_activity_payload(payload)
        self.assertEqual(normalized["tipo_deporte"], "BIKE")


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
        calories_kcal: float | None = None,
        relative_effort: float | None = None,
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
        # Opcionales (pueden faltar y deben quedar NULL, no 0)
        self.calories = calories_kcal
        self.relative_effort = relative_effort
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


class _FakeStravaClientWithStreams(_FakeStravaClient):
    def __init__(self, activity: _FakeStravaActivity, *, altitude_stream: list[float]):
        super().__init__(activity)
        self._altitude_stream = altitude_stream

    def get_activity_streams(self, activity_id: int, types=None, *args, **kwargs):
        assert int(activity_id) == int(self._activity.id)
        return {"altitude": {"data": list(self._altitude_stream)}}


@override_settings(STRAVA_WEBHOOK_SUBSCRIPTION_ID=1)
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

    def test_missing_calories_is_estimated(self):
        """
        Si Strava no trae calories, estimamos kcal para evitar NULL en analytics.
        """
        start = datetime.now(dt_timezone.utc)
        a = _FakeStravaActivity(
            activity_id=7001,
            athlete_id=111,
            name="No Calories Run",
            type_="Run",
            start=start,
            distance_m=5000,
            moving_time_s=1500,
            elev_m=10,
            calories_kcal=None,
        )
        e = self._mk_event(uid="e_cal_none", owner_id=111, object_id=7001, aspect="create")
        with patch("core.services.obtener_cliente_strava", return_value=_FakeStravaClient(a)):
            process_strava_event.delay(e.id)

        act = Actividad.objects.get(strava_id=7001)
        self.assertIsNotNone(act.calories_kcal)
        self.assertGreater(act.calories_kcal, 0)

    def test_elev_loss_computed_when_alt_stream_present(self):
        """
        Si Strava no trae elev_loss, lo calculamos desde stream de altitud (best-effort).
        """
        start = datetime.now(dt_timezone.utc)
        a = _FakeStravaActivity(
            activity_id=7002,
            athlete_id=111,
            name="Alt Stream Run",
            type_="Run",
            start=start,
            distance_m=8000,
            moving_time_s=2400,
            elev_m=200,
        )
        altitude = [100, 110, 105, 90, 95]
        e = self._mk_event(uid="e_alt", owner_id=111, object_id=7002, aspect="create")
        with patch(
            "core.services.obtener_cliente_strava",
            return_value=_FakeStravaClientWithStreams(a, altitude_stream=altitude),
        ):
            process_strava_event.delay(e.id)

        act = Actividad.objects.get(strava_id=7002)
        self.assertIsNotNone(act.elev_loss_m)
        self.assertAlmostEqual(float(act.elev_loss_m), 12.5, places=1)
        self.assertAlmostEqual(float(act.elev_gain_m), 200.0, places=1)
        self.assertAlmostEqual(float(act.elev_total_m), 212.5, places=1)

    def test_elevation_policy_gain_only_defaults_loss(self):
        start = datetime.now(dt_timezone.utc)
        a = _FakeStravaActivity(
            activity_id=7003,
            athlete_id=111,
            name="Gain Only Run",
            type_="Run",
            start=start,
            distance_m=6000,
            moving_time_s=1800,
            elev_m=150,
            calories_kcal=320,
        )
        e = self._mk_event(uid="e_gain_only", owner_id=111, object_id=7003, aspect="create")
        with patch("core.services.obtener_cliente_strava", return_value=_FakeStravaClient(a)):
            process_strava_event.delay(e.id)

        act = Actividad.objects.get(strava_id=7003)
        self.assertAlmostEqual(float(act.elev_gain_m), 150.0, places=1)
        self.assertAlmostEqual(float(act.elev_loss_m), 0.0, places=1)
        self.assertAlmostEqual(float(act.elev_total_m), 150.0, places=1)
        self.assertAlmostEqual(float(act.calories_kcal), 320.0, places=1)

    def test_elevation_policy_missing_data_defaults_to_zero(self):
        start = datetime.now(dt_timezone.utc)
        a = _FakeStravaActivity(
            activity_id=7004,
            athlete_id=111,
            name="No Elevation Run",
            type_="Run",
            start=start,
            distance_m=4000,
            moving_time_s=1200,
            elev_m=None,
            calories_kcal=None,
        )
        e = self._mk_event(uid="e_no_elev", owner_id=111, object_id=7004, aspect="create")
        with patch("core.services.obtener_cliente_strava", return_value=_FakeStravaClient(a)):
            process_strava_event.delay(e.id)

        act = Actividad.objects.get(strava_id=7004)
        self.assertAlmostEqual(float(act.elev_gain_m), 0.0, places=1)
        self.assertAlmostEqual(float(act.elev_loss_m), 0.0, places=1)
        self.assertAlmostEqual(float(act.elev_total_m), 0.0, places=1)
        self.assertIsNotNone(act.calories_kcal)

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

    def test_bike_activity_is_normalized_and_created(self):
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
        self.assertEqual(act.validity, Actividad.Validity.VALID)
        self.assertEqual(act.invalid_reason, "")
        self.assertEqual(act.tipo_deporte, "BIKE")
        self.assertEqual(Entrenamiento.objects.filter(strava_id="777").count(), 1)
        self.assertTrue(
            StravaImportLog.objects.filter(event=e, status=StravaImportLog.Status.SAVED).exists()
        )

    def test_walk_activity_with_zero_distance_is_discarded(self):
        """
        WALK with distance=0 must be DISCARDED (PR-182: distance required for
        distance-based sports including WALK).
        """
        start = datetime.now(dt_timezone.utc)
        walk = _FakeStravaActivity(
            activity_id=778,
            athlete_id=111,
            name="Walk",
            type_="Walk",
            start=start,
            distance_m=0,
            moving_time_s=900,
        )
        e = self._mk_event(uid="e_walk_nodist", owner_id=111, object_id=778, aspect="create")

        with patch("core.services.obtener_cliente_strava", return_value=_FakeStravaClient(walk)):
            process_strava_event.delay(e.id)

        act = Actividad.objects.get(strava_id=778)
        self.assertEqual(act.validity, Actividad.Validity.DISCARDED)
        self.assertIn("distance_non_positive_for_WALK", act.invalid_reason)
        self.assertEqual(Entrenamiento.objects.filter(strava_id="778").count(), 0)
        self.assertTrue(
            StravaImportLog.objects.filter(
                event=e,
                status=StravaImportLog.Status.DISCARDED,
                reason="distance_non_positive_for_WALK",
            ).exists()
        )

    def test_walk_activity_with_distance_is_created_valid(self):
        """
        WALK with distance>0 and duration>0 must be VALID (PR-182 relaxed
        creation gate: "todo suma"; distance required only for distance-based
        sports, duration > 0 is the universal gate).
        """
        start = datetime.now(dt_timezone.utc)
        walk = _FakeStravaActivity(
            activity_id=779,
            athlete_id=111,
            name="Walk",
            type_="Walk",
            start=start,
            distance_m=3000,
            moving_time_s=1800,
        )
        e = self._mk_event(uid="e_walk_valid", owner_id=111, object_id=779, aspect="create")

        with patch("core.services.obtener_cliente_strava", return_value=_FakeStravaClient(walk)):
            process_strava_event.delay(e.id)

        act = Actividad.objects.get(strava_id=779)
        self.assertEqual(act.validity, Actividad.Validity.VALID)
        self.assertEqual(act.invalid_reason, "")
        self.assertTrue(
            StravaImportLog.objects.filter(event=e, status=StravaImportLog.Status.SAVED).exists()
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


class LegacyStravaSyncGuardrailTests(TestCase):
    @override_settings(DISABLE_LEGACY_STRAVA_SYNC=True)
    def test_legacy_sync_blocked_in_production(self):
        user = User.objects.create_user(username="legacy_blocked", password="x")
        with patch("core.services.obtener_cliente_strava") as get_client:
            with self.assertRaises(LegacyStravaSyncDisabled):
                sincronizar_actividades_strava(user)

        get_client.assert_not_called()
        self.assertEqual(Actividad.objects.count(), 0)

    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        CELERY_TASK_EAGER_PROPAGATES=True,
        DISABLE_LEGACY_STRAVA_SYNC=True,
    )
    def test_modern_pipeline_still_runs_with_legacy_disabled(self):
        coach = User.objects.create_user(username="coach_modern", password="x")
        alumno = Alumno.objects.create(
            entrenador=coach,
            nombre="Ana",
            apellido="Modern",
            email="ana_modern@test.com",
            strava_athlete_id="333",
        )
        start = datetime.now(dt_timezone.utc)
        run = _FakeStravaActivity(
            activity_id=3333,
            athlete_id=333,
            name="Modern Run",
            type_="Run",
            start=start,
            distance_m=7000,
            moving_time_s=2100,
        )
        event = StravaWebhookEvent.objects.create(
            event_uid="modern_legacy_disabled",
            object_type="activity",
            object_id=3333,
            aspect_type="create",
            owner_id=333,
            subscription_id=1,
            payload_raw={"test": True},
            status=StravaWebhookEvent.Status.QUEUED,
        )

        with patch("core.services.obtener_cliente_strava", return_value=_FakeStravaClient(run)):
            process_strava_event.delay(event.id)

        self.assertEqual(Actividad.objects.filter(alumno=alumno, strava_id=3333).count(), 1)


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


class LoggingExtraSafetyTests(TestCase):
    def test_strava_activity_upserted_extra_uses_no_reserved_logrecord_keys(self):
        extra = _build_strava_activity_upserted_extra(
            alumno_id=7,  # explicit: do not use athlete 138463792; keep to admin athlete id=7
            source="strava",
            source_object_id="123",
            upsert_created=True,
            payload_sanitized=False,
        )
        self.assertTrue(RESERVED_LOGRECORD_ATTRS.isdisjoint(extra.keys()))
        # Contract: preserve meaning of upsert result
        self.assertIn("upsert_created", extra)
        self.assertEqual(extra["upsert_created"], True)

    def test_strava_activity_upserted_logger_does_not_raise_keyerror_and_includes_upsert_created(self):
        class _Capture(logging.Handler):
            def __init__(self):
                super().__init__()
                self.records = []

            def emit(self, record):
                self.records.append(record)

        capture = _Capture()
        from core import tasks as tasks_module

        tasks_logger = tasks_module.logger
        prev_level = tasks_logger.level
        prev_propagate = tasks_logger.propagate
        tasks_logger.setLevel(logging.INFO)
        tasks_logger.propagate = False
        tasks_logger.addHandler(capture)
        try:
            # This must not raise (KeyError would crash Celery).
            _log_strava_activity_upserted(
                alumno_id=7,
                source="strava",
                source_object_id="123",
                upsert_created=True,
                payload_sanitized=False,
            )
        finally:
            tasks_logger.removeHandler(capture)
            tasks_logger.setLevel(prev_level)
            tasks_logger.propagate = prev_propagate

        rec = next(r for r in capture.records if r.msg == "strava.activity.upserted")
        self.assertTrue(hasattr(rec, "upsert_created"))
        self.assertEqual(rec.upsert_created, True)

class StravaUpsertTests(TestCase):
    def setUp(self):
        self.coach = User.objects.create_user(username="coach_upsert", password="x")
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Ana",
            apellido="Upsert",
            email="ana_upsert@test.com",
            strava_athlete_id="999",
        )
        self.alumno_no_coach = Alumno.objects.create(
            entrenador=None,
            nombre="Beto",
            apellido="NoCoach",
            email="beto_nocoach@test.com",
        )

    def test_upsert_fails_without_usuario(self):
        from core.actividad_upsert import upsert_actividad
        
        with self.assertRaises(ValueError) as cm:
            upsert_actividad(
                alumno=self.alumno_no_coach,
                usuario=None,
                source="strava",
                source_object_id="123",
                defaults={
                    "nombre": "Test",
                    "distancia": 1000,
                    "tiempo_movimiento": 600,
                    "fecha_inicio": timezone.now(),
                    "tipo_deporte": "RUN",
                    "validity": "VALID",
                }
            )
        self.assertTrue("usuario" in str(cm.exception))

    def test_upsert_succeeds_with_usuario(self):
        from core.actividad_upsert import upsert_actividad
        
        act, created = upsert_actividad(
            alumno=self.alumno,
            usuario=self.coach,
            source="strava",
            source_object_id="456",
            defaults={
                "nombre": "Test 2",
                "distancia": 2000,
                "tiempo_movimiento": 1200,
                "fecha_inicio": timezone.now(),
                "tipo_deporte": "BIKE",
                "validity": "VALID",
            }
        )
        self.assertTrue(created)
        self.assertEqual(act.usuario_id, self.coach.id)

class StravaTenantResolutionTests(TestCase):
    def setUp(self):
        self.coach = User.objects.create_user(username="coach_tenant", password="x")
        self.user_orphan1 = User.objects.create_user(username="user_orphan1", password="x")
        self.user_orphan2 = User.objects.create_user(username="user_orphan2", password="x")
        
        self.alumno_with_coach = Alumno.objects.create(
            entrenador=self.coach,
            usuario=self.user_orphan1,
            nombre="Ana",
            apellido="Coach",
            email="ana_coach@test.com",
            strava_athlete_id="1010",
        )
        
        self.alumno_with_user = Alumno.objects.create(
            entrenador=None,
            usuario=self.user_orphan2,
            nombre="Beto",
            apellido="User",
            email="beto_user@test.com",
            strava_athlete_id="2020",
        )
        
        self.alumno_orphan = Alumno.objects.create(
            entrenador=None,
            usuario=None,
            nombre="Carlos",
            apellido="Orphan",
            email="carlos_orphan@test.com",
            strava_athlete_id="3030",
        )

    def _mk_event(self, *, uid: str, owner_id: int, object_id: int):
        return StravaWebhookEvent.objects.create(
            event_uid=uid,
            object_type="activity",
            object_id=object_id,
            aspect_type="create",
            owner_id=owner_id,
            subscription_id=1,
            payload_raw={"test": True},
            status=StravaWebhookEvent.Status.QUEUED,
        )

    def test_tenant_resolves_to_entrenador_when_present(self):
        start = datetime.now(dt_timezone.utc)
        a = _FakeStravaActivity(
            activity_id=7771,
            athlete_id=1010,
            name="Run",
            type_="Run",
            start=start,
            distance_m=1000,
            moving_time_s=600,
        )
        e = self._mk_event(uid="ev1", owner_id=1010, object_id=7771)
        with patch("core.services.obtener_cliente_strava_para_alumno", return_value=_FakeStravaClient(a)):
            process_strava_event(e.id)
            
        act = Actividad.objects.filter(strava_id=7771).first()
        self.assertIsNotNone(act)
        self.assertEqual(act.usuario_id, self.coach.id)

    def test_tenant_resolves_to_alumno_usuario_when_no_entrenador(self):
        start = datetime.now(dt_timezone.utc)
        a = _FakeStravaActivity(
            activity_id=7772,
            athlete_id=2020,
            name="Run",
            type_="Run",
            start=start,
            distance_m=1000,
            moving_time_s=600,
        )
        e = self._mk_event(uid="ev2", owner_id=2020, object_id=7772)
        with patch("core.services.obtener_cliente_strava_para_alumno", return_value=_FakeStravaClient(a)):
            process_strava_event(e.id)
            
        act = Actividad.objects.filter(strava_id=7772).first()
        self.assertIsNotNone(act)
        self.assertEqual(act.usuario_id, self.user_orphan2.id)

    def test_missing_tenant_returns_deferred_without_exception(self):
        start = datetime.now(dt_timezone.utc)
        a = _FakeStravaActivity(
            activity_id=7773,
            athlete_id=3030,
            name="Run",
            type_="Run",
            start=start,
            distance_m=1000,
            moving_time_s=600,
        )
        e = self._mk_event(uid="ev3", owner_id=3030, object_id=7773)
        with patch("core.services.obtener_cliente_strava_para_alumno", return_value=_FakeStravaClient(a)):
            result = process_strava_event(e.id)
            
        self.assertEqual(result, "DEFERRED: missing_tenant")
        act = Actividad.objects.filter(strava_id=7773).first()
        self.assertIsNone(act)

class CeleryFailureHandlerTests(TestCase):
    def test_log_critical_task_failure_never_raises_keyerror(self):
        from backend.celery import log_critical_task_failure
        import logging
        
        class MockSender:
            name = "strava.test"
            
        try:
            log_critical_task_failure(
                sender=MockSender(), 
                task_id="123", 
                exception=ValueError("test error"), 
                args=(1, 2), 
                kwargs={"a": "b"}
            )
        except Exception as e:
            self.fail(f"log_critical_task_failure raised exception: {e}")


# ==============================================================================
# PR20: OAuthCredential as primary credential source — protective tests
# ==============================================================================

@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class PR20OAuthCredentialPrimaryTests(TestCase):
    """
    Test 1: strava.process_event uses OAuthCredential when present.

    Ensures that if OAuthCredential exists for the alumno, the worker calls
    obtener_cliente_strava_para_alumno() successfully (via OAuthCredential path),
    without needing an allauth SocialToken.
    """

    def setUp(self):
        from core.models import OAuthCredential
        self.coach = User.objects.create_user(username="coach_pr20_primary", password="x")
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Ana",
            apellido="PR20",
            email="ana_pr20@test.com",
            strava_athlete_id="55500",
        )
        # Populate OAuthCredential (no allauth SocialToken created)
        self.cred = OAuthCredential.objects.create(
            alumno=self.alumno,
            provider="strava",
            external_user_id="55500",
            access_token="tok_primary_abc",
            refresh_token="ref_primary_xyz",
            expires_at=timezone.now() + timezone.timedelta(hours=6),
        )

    def _mk_event(self, *, uid, owner_id, object_id):
        return StravaWebhookEvent.objects.create(
            event_uid=uid,
            object_type="activity",
            object_id=object_id,
            aspect_type="create",
            owner_id=owner_id,
            subscription_id=1,
            payload_raw={"test": True},
            status=StravaWebhookEvent.Status.QUEUED,
        )

    def test_process_event_uses_oauthcredential_when_present(self):
        """
        GIVEN: OAuthCredential(strava) exists; no allauth SocialToken.
        WHEN: process_strava_event is called.
        THEN: Activity is imported (worker resolved client from OAuthCredential).
        """
        from datetime import datetime as _dt
        start = _dt.now(dt_timezone.utc)
        activity = _FakeStravaActivity(
            activity_id=55501,
            athlete_id=55500,
            name="PR20 Primary Run",
            type_="Run",
            start=start,
            distance_m=7000,
            moving_time_s=2100,
        )
        event = self._mk_event(uid="pr20_primary_e1", owner_id=55500, object_id=55501)

        # Patch at the function-level inside services, which is where OAuthCredential path
        # returns a client. We patch obtener_cliente_strava_para_alumno directly to verify
        # it is called and returns a valid client (avoids needing stravalib to be real).
        with patch(
            "core.services.obtener_cliente_strava_para_alumno",
            return_value=_FakeStravaClient(activity),
        ) as mock_client:
            process_strava_event.delay(event.id)

        mock_client.assert_called_once()
        self.assertEqual(Actividad.objects.filter(strava_id=55501).count(), 1)
        event.refresh_from_db()
        self.assertIn(event.status, [
            StravaWebhookEvent.Status.PROCESSED,
            "processed",
        ])


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class PR20OAuthCredentialFallbackTests(TestCase):
    """
    Test 2: fallback to allauth SocialToken when OAuthCredential absent.

    Ensures reason_code CRED_FALLBACK_ALLAUTH is logged and the flow completes
    when only SocialToken is present (backward compat preserved).
    """

    def setUp(self):
        self.coach = User.objects.create_user(username="coach_pr20_fallback", password="x")
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            nombre="Beto",
            apellido="PR20fb",
            email="beto_pr20@test.com",
            strava_athlete_id="55600",
        )
        # No OAuthCredential created → forces fallback path

    def _mk_event(self, *, uid, owner_id, object_id):
        return StravaWebhookEvent.objects.create(
            event_uid=uid,
            object_type="activity",
            object_id=object_id,
            aspect_type="create",
            owner_id=owner_id,
            subscription_id=1,
            payload_raw={"test": True},
            status=StravaWebhookEvent.Status.QUEUED,
        )

    def test_fallback_to_allauth_when_oauthcredential_absent(self):
        """
        GIVEN: No OAuthCredential; allauth SocialToken exists (mock).
        WHEN: obtener_cliente_strava_para_alumno is called.
        THEN: Returns a valid client via the allauth-SocialToken fallback path.
        """
        from datetime import datetime as _dt
        start = _dt.now(dt_timezone.utc)
        activity = _FakeStravaActivity(
            activity_id=55601,
            athlete_id=55600,
            name="PR20 Fallback Run",
            type_="Run",
            start=start,
            distance_m=5000,
            moving_time_s=1500,
        )

        import logging as _logging
        log_records = []

        class _Capture(_logging.Handler):
            def emit(self, record):
                log_records.append(record)

        capture = _Capture()
        capture.setLevel(_logging.DEBUG)
        import core.services as _svc_module
        svc_logger = _svc_module.logger
        original_level = svc_logger.level
        svc_logger.setLevel(_logging.DEBUG)
        svc_logger.addHandler(capture)

        try:
            # Simulate: obtener_cliente_strava (allauth path) returns a fake client.
            with patch(
                "core.services.obtener_cliente_strava",
                return_value=_FakeStravaClient(activity),
            ):
                from core.services import obtener_cliente_strava_para_alumno
                result = obtener_cliente_strava_para_alumno(self.alumno)

            self.assertIsNotNone(result, "Expected a client via fallback path")

            # Verify CRED_FALLBACK_ALLAUTH was logged (reason_code attr set by safe_extra)
            fallback_records = [
                r for r in log_records
                if getattr(r, "reason_code", None) == "CRED_FALLBACK_ALLAUTH"
            ]
            self.assertTrue(
                len(fallback_records) > 0,
                f"Expected CRED_FALLBACK_ALLAUTH log. Got reason_codes: "
                f"{[getattr(r, 'reason_code', None) for r in log_records]}",
            )
        finally:
            svc_logger.removeHandler(capture)
            svc_logger.setLevel(original_level)


class PR20OAuthCallbackPersistsCredentialTests(TestCase):
    """
    Test 3: OAuth callback persists OAuthCredential.

    Simulates the integration callback and verifies that after a successful
    token exchange, OAuthCredential is created/updated with the correct fields.
    This does NOT test allauth at all — only our custom callback view via
    the helper method _handle_generic_callback on IntegrationCallbackView.
    """

    def setUp(self):
        self.coach = User.objects.create_user(username="coach_pr20_cb", password="x")
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            usuario=self.coach,  # usuario = coach for simplicity
            nombre="Clara",
            apellido="PR20cb",
            email="clara_pr20@test.com",
        )

    def test_oauth_callback_persists_oauthcredential(self):
        """
        GIVEN: A successful token exchange with Strava.
        WHEN:  persist_oauth_tokens_v2 is called (as done inside the callback).
        THEN:  OAuthCredential(provider=strava, alumno=self.alumno) is created with
               correct external_user_id, access_token, refresh_token, and expires_at.
        """
        from core.models import OAuthCredential
        from core.oauth_credentials import persist_oauth_tokens_v2
        from datetime import datetime as _dt, timezone as _tz

        expires_ts = int(timezone.now().timestamp()) + 21600  # +6h
        expires_dt = _dt.fromtimestamp(expires_ts, tz=_tz.utc)

        result = persist_oauth_tokens_v2(
            provider="strava",
            alumno=self.alumno,
            token_data={
                "access_token": "fake_access_abc",
                "refresh_token": "fake_refresh_xyz",
                "expires_at": expires_dt,
            },
            external_user_id="77700",
        )

        self.assertTrue(result.success, f"persist_oauth_tokens_v2 failed: {result.error_reason}")

        cred = OAuthCredential.objects.filter(alumno=self.alumno, provider="strava").first()
        self.assertIsNotNone(cred, "OAuthCredential should have been created after OAuth callback")
        self.assertEqual(cred.external_user_id, "77700")
        self.assertEqual(cred.access_token, "fake_access_abc")
        self.assertEqual(cred.refresh_token, "fake_refresh_xyz")
        self.assertIsNotNone(cred.expires_at)


# ==============================================================================
#  PR21: Disconnect Strava — protective tests
# ==============================================================================

class StravaDisconnectTests(TestCase):
    """
    Protective tests for DELETE /api/integrations/strava/disconnect/

    Coverage:
    - test_disconnect_purges_tokens_and_marks_identity_disabled
    - test_disconnect_idempotent
    - test_worker_auth_after_disconnect_returns_none
    - test_no_token_in_logs
    """

    def setUp(self):
        self.coach = User.objects.create_user(username="coach_disc21", password="x")
        self.athlete_user = User.objects.create_user(username="athlete_disc21", password="x")
        self.alumno = Alumno.objects.create(
            entrenador=self.coach,
            usuario=self.athlete_user,
            nombre="Disco",
            apellido="Test",
            email="disco_test21@test.com",
            strava_athlete_id="54321",
        )
        from core.integration_models import OAuthIntegrationStatus
        OAuthIntegrationStatus.objects.create(
            alumno=self.alumno,
            provider="strava",
            connected=True,
            athlete_id="54321",
            status=OAuthIntegrationStatus.Status.CONNECTED,
        )

    def _seed_oauth_credential(self, access_token="tok_access", refresh_token="tok_refresh"):
        from core.models import OAuthCredential
        OAuthCredential.objects.update_or_create(
            alumno=self.alumno,
            provider="strava",
            defaults={
                "external_user_id": "54321",
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": timezone.now() + timezone.timedelta(hours=6),
            },
        )

    def test_disconnect_purges_tokens_and_marks_identity_disabled(self):
        """
        GIVEN: OAuthCredential and ExternalIdentity exist for the alumno.
        WHEN:  DELETE /api/integrations/strava/disconnect/ (Strava revoke mocked OK).
        THEN:  OAuthCredential deleted, ExternalIdentity DISABLED, OAuthIntegrationStatus DISCONNECTED, 204.
        """
        from core.models import OAuthCredential, ExternalIdentity
        from core.integration_models import OAuthIntegrationStatus

        self._seed_oauth_credential()
        ExternalIdentity.objects.get_or_create(
            provider="strava",
            external_user_id="54321",
            defaults={
                "alumno": self.alumno,
                "status": ExternalIdentity.Status.LINKED,
            },
        )

        self.client.force_login(self.athlete_user)

        with patch("requests.post") as mock_post:
            from unittest.mock import MagicMock
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp
            res = self.client.delete("/api/integrations/strava/disconnect/")

        self.assertEqual(res.status_code, 204, f"Expected 204, got {res.status_code}: {getattr(res, 'content', b'')}")

        # OAuthCredential must be gone
        self.assertFalse(
            OAuthCredential.objects.filter(alumno=self.alumno, provider="strava").exists(),
            "OAuthCredential must be purged after disconnect",
        )

        # ExternalIdentity must be DISABLED
        identity = ExternalIdentity.objects.filter(alumno=self.alumno, provider="strava").first()
        self.assertIsNotNone(identity)
        self.assertEqual(identity.status, ExternalIdentity.Status.DISABLED)

        # OAuthIntegrationStatus must be DISCONNECTED
        ois = OAuthIntegrationStatus.objects.filter(alumno=self.alumno, provider="strava").first()
        self.assertIsNotNone(ois)
        self.assertFalse(ois.connected)
        self.assertEqual(ois.status, OAuthIntegrationStatus.Status.DISCONNECTED)

        # Alumno.strava_athlete_id must be cleared
        self.alumno.refresh_from_db()
        self.assertIsNone(self.alumno.strava_athlete_id)

    def test_disconnect_idempotent(self):
        """
        GIVEN: No OAuthCredential, no SocialAccount, no LINKED ExternalIdentity (already disconnected).
        WHEN:  DELETE /api/integrations/strava/disconnect/ called twice.
        THEN:  Both calls return 204.
        """
        self.client.force_login(self.athlete_user)
        res1 = self.client.delete("/api/integrations/strava/disconnect/")
        self.assertEqual(res1.status_code, 204, f"First idempotent call: expected 204, got {res1.status_code}")
        res2 = self.client.delete("/api/integrations/strava/disconnect/")
        self.assertEqual(res2.status_code, 204, f"Second idempotent call: expected 204, got {res2.status_code}")

    def test_worker_auth_after_disconnect_returns_none(self):
        """
        GIVEN: OAuthCredential seeded for alumno.
        WHEN:  OAuthCredential is deleted (as disconnect does).
        THEN:  obtener_cliente_strava_para_alumno(alumno) returns None.
        """
        from core.models import OAuthCredential
        from core.services import obtener_cliente_strava_para_alumno

        self._seed_oauth_credential()
        self.assertTrue(OAuthCredential.objects.filter(alumno=self.alumno, provider="strava").exists())

        OAuthCredential.objects.filter(alumno=self.alumno, provider="strava").delete()

        client = obtener_cliente_strava_para_alumno(self.alumno)
        self.assertIsNone(client, "Worker must not authenticate after disconnect purges OAuthCredential")

    def test_no_token_in_logs(self):
        """
        GIVEN: OAuthCredential with a canary access_token value.
        WHEN:  Disconnect endpoint called.
        THEN:  The canary value never appears in any WARNING+ log record.
        """
        import logging as _logging
        from unittest.mock import MagicMock

        SECRET_TOKEN = "SUPER_SECRET_ACCESS_TOKEN_CANARY_PR21"
        self._seed_oauth_credential(access_token=SECRET_TOKEN)

        class _SecretCapture(_logging.Handler):
            def __init__(self):
                super().__init__()
                self.found_secret = False

            def emit(self, record):
                try:
                    msg = self.format(record)
                except Exception:
                    msg = str(record.getMessage())
                if SECRET_TOKEN in msg:
                    self.found_secret = True

        capture = _SecretCapture()
        capture.setLevel(_logging.WARNING)
        root_logger = _logging.getLogger()
        root_logger.addHandler(capture)

        try:
            self.client.force_login(self.athlete_user)
            with patch("requests.post") as mock_post:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_post.return_value = mock_resp
                self.client.delete("/api/integrations/strava/disconnect/")
        finally:
            root_logger.removeHandler(capture)

        self.assertFalse(
            capture.found_secret,
            "access_token must NEVER appear in WARNING+ log records during disconnect",
        )


class ObtenerClienteStravaLegacyTests(TestCase):
    """
    PR-122: Unit tests for the legacy `obtener_cliente_strava()` function.

    Coverage:
    - test_valid_token_returns_client: happy path — non-expired token returns a configured Client.
    - test_expired_token_refresh_failure_returns_none_and_logs: inner except path — TOKEN_REFRESH_ERROR emitted.
    - test_outer_exception_returns_none_and_logs: outer except path — TOKEN_LOOKUP_ERROR emitted.
    """

    def setUp(self):
        from allauth.socialaccount.models import SocialApp, SocialAccount, SocialToken as _SocialToken

        self.user = User.objects.create_user(username="legacy_strava_pr122", password="x")

        self.social_app = SocialApp.objects.create(
            provider="strava",
            name="Strava",
            client_id="test_client_id",
            secret="test_secret",
        )

        self.social_account = SocialAccount.objects.create(
            user=self.user,
            provider="strava",
            uid="99999",
        )

        self.social_token = _SocialToken.objects.create(
            account=self.social_account,
            app=self.social_app,
            token="access_tok_pr122",
            token_secret="refresh_tok_pr122",
            expires_at=timezone.now() + timezone.timedelta(hours=6),
        )

    def _capture_services_logger(self):
        """Return (handler, log_records list) for core.services logger."""
        import logging as _logging
        import core.services as _svc

        records = []

        class _Capture(_logging.Handler):
            def emit(self, record):
                records.append(record)

        h = _Capture()
        h.setLevel(_logging.WARNING)
        _svc.logger.addHandler(h)
        return h, records, _svc.logger

    def test_valid_token_returns_client(self):
        """
        GIVEN: A non-expired SocialToken for the user.
        WHEN:  obtener_cliente_strava(user) is called.
        THEN:  Returns a stravalib Client with access_token set; no error logged.
        """
        from core.services import obtener_cliente_strava

        result = obtener_cliente_strava(self.user)

        self.assertIsNotNone(result, "Expected a valid Client for non-expired token")
        self.assertEqual(result.access_token, "access_tok_pr122")

    def test_expired_token_refresh_failure_returns_none_and_logs(self):
        """
        GIVEN: An expired SocialToken; client.refresh_access_token raises RuntimeError.
        WHEN:  obtener_cliente_strava(user) is called.
        THEN:  Returns None and emits a WARNING with event_name=strava.token.refresh_failed,
               reason_code=TOKEN_REFRESH_ERROR, provider=strava, outcome=fail.
               No token value appears in the log record.
        """
        from core.services import obtener_cliente_strava

        self.social_token.expires_at = timezone.now() - timezone.timedelta(hours=1)
        self.social_token.save()

        h, records, svc_logger = self._capture_services_logger()
        try:
            with patch("core.services.Client") as MockClient:
                fake_client = MockClient.return_value
                fake_client.access_token = "access_tok_pr122"
                fake_client.refresh_token = "refresh_tok_pr122"
                fake_client.refresh_access_token.side_effect = RuntimeError("401 Unauthorized")

                result = obtener_cliente_strava(self.user)
        finally:
            svc_logger.removeHandler(h)

        self.assertIsNone(result, "Expected None on token refresh failure")

        matching = [
            r for r in records
            if getattr(r, "event_name", None) == "strava.token.refresh_failed"
        ]
        self.assertTrue(
            len(matching) > 0,
            f"Expected strava.token.refresh_failed log. Got event_names: "
            f"{[getattr(r, 'event_name', None) for r in records]}",
        )
        record = matching[0]
        self.assertEqual(getattr(record, "reason_code", None), "TOKEN_REFRESH_ERROR")
        self.assertEqual(getattr(record, "provider", None), "strava")
        self.assertEqual(getattr(record, "outcome", None), "fail")
        # Law 6: no token value in the log message
        msg = record.getMessage()
        self.assertNotIn("access_tok_pr122", msg)
        self.assertNotIn("refresh_tok_pr122", msg)

    def test_outer_exception_returns_none_and_logs(self):
        """
        GIVEN: SocialToken.objects.filter raises an unexpected exception (DB error simulated).
        WHEN:  obtener_cliente_strava(user) is called.
        THEN:  Returns None and emits a WARNING with event_name=strava.token.lookup_failed,
               reason_code=TOKEN_LOOKUP_ERROR, provider=strava, outcome=fail.
        """
        from core.services import obtener_cliente_strava

        h, records, svc_logger = self._capture_services_logger()
        try:
            with patch(
                "core.services.SocialToken.objects.filter",
                side_effect=Exception("DB unavailable"),
            ):
                result = obtener_cliente_strava(self.user)
        finally:
            svc_logger.removeHandler(h)

        self.assertIsNone(result, "Expected None when outer exception occurs")

        matching = [
            r for r in records
            if getattr(r, "event_name", None) == "strava.token.lookup_failed"
        ]
        self.assertTrue(
            len(matching) > 0,
            f"Expected strava.token.lookup_failed log. Got event_names: "
            f"{[getattr(r, 'event_name', None) for r in records]}",
        )
        record = matching[0]
        self.assertEqual(getattr(record, "reason_code", None), "TOKEN_LOOKUP_ERROR")
        self.assertEqual(getattr(record, "provider", None), "strava")
        self.assertEqual(getattr(record, "outcome", None), "fail")
