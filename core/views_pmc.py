"""
core/views_pmc.py

PMC (Performance Management Chart) API views — PR-128a / PR-152.

Endpoints:
    GET  /api/athlete/pmc/               — athlete reads own PMC from DailyLoad
    GET  /api/coach/athletes/<m_id>/pmc/ — coach reads any athlete's PMC
    GET  /api/coach/team-readiness/      — coach reads team TSB summary
    GET  /api/athlete/hr-profile/        — athlete reads own HR profile
    PUT  /api/athlete/hr-profile/        — athlete updates own HR profile
    GET  /api/coach/athletes/<m_id>/training-volume/ — volume buckets by sport/metric
    GET  /api/coach/athletes/<m_id>/wellness/        — wellness check-in history
    GET  /api/coach/athletes/<m_id>/compliance/      — plan vs actual compliance

Tenancy: organization is resolved from the authenticated user's active Membership.
For users with a single org membership, resolution is automatic. For multi-org
users, ?org_id=<pk> is required to avoid non-deterministic selection (PR-149).
Law 6: no PII logged (user IDs only, no names/emails).
"""
import logging
import math as _math
from datetime import timedelta

from django.db.models import Avg, Count, FloatField, Max, Q, Sum
from django.db.models.functions import TruncMonth, TruncWeek
from django.utils import timezone

from core.services_gap import compute_gap, format_pace as _fmt_gap_pace

from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import (
    Alumno,
    Athlete,
    AthleteCoachAssignment,
    AthleteHRProfile,
    Coach,
    CompletedActivity,
    DailyLoad,
    Membership,
    WellnessCheckIn,
    WorkoutAssignment,
)

logger = logging.getLogger(__name__)

_COACH_ROLES = frozenset(["owner", "coach"])
_TSB_ZONE_LABELS = {
    "fresh": "Muy fresco",
    "optimal": "Ventana óptima",
    "productive": "Carga productiva",
    "fatigued": "Fatiga acumulada",
    "overreaching": "Sobreentrenamiento",
}


def _get_athlete_membership(request):
    """
    Resolve the requesting user's active athlete Membership.

    PR-149: Fixed non-deterministic org selection. If a user is an athlete in
    multiple organizations, ?org_id=<pk> must be supplied to disambiguate.
    Raises 400 (ValidationError) if ambiguous and org_id not provided.
    Raises 403 (PermissionDenied) if no matching membership exists.
    """
    memberships = list(
        Membership.objects
        .select_related("organization")
        .filter(user=request.user, role=Membership.Role.ATHLETE, is_active=True)
    )
    if not memberships:
        raise PermissionDenied("No active athlete membership found.")
    if len(memberships) == 1:
        return memberships[0]
    # Multi-org athlete: require explicit org_id query param
    # Use getattr to support both DRF Request (query_params) and raw WSGIRequest (GET)
    query_params = getattr(request, "query_params", request.GET)
    org_id = query_params.get("org_id")
    if not org_id:
        raise ValidationError(
            {"org_id": "Multiple athlete memberships found. Provide ?org_id= to specify the organization."}
        )
    try:
        org_id = int(org_id)
    except (TypeError, ValueError):
        raise ValidationError({"org_id": "Must be an integer."})
    matched = [m for m in memberships if m.organization_id == org_id]
    if not matched:
        raise PermissionDenied("No active athlete membership found in the specified organization.")
    return matched[0]


def _get_coach_membership(request):
    """
    Resolve the requesting user's active coach/owner Membership.

    PR-149: Fixed non-deterministic org selection. If a user holds coach/owner
    roles in multiple organizations, ?org_id=<pk> must be supplied.
    Raises 400 (ValidationError) if ambiguous and org_id not provided.
    Raises 403 (PermissionDenied) if no matching membership exists.
    """
    memberships = list(
        Membership.objects
        .select_related("organization")
        .filter(
            user=request.user,
            role__in=[Membership.Role.OWNER, Membership.Role.COACH],
            is_active=True,
        )
    )
    if not memberships:
        raise PermissionDenied("No active coach or owner membership found.")
    if len(memberships) == 1:
        return memberships[0]
    # Multi-org coach: require explicit org_id query param
    # Use getattr to support both DRF Request (query_params) and raw WSGIRequest (GET)
    query_params = getattr(request, "query_params", request.GET)
    org_id = query_params.get("org_id")
    if not org_id:
        raise ValidationError(
            {"org_id": "Multiple coach memberships found. Provide ?org_id= to specify the organization."}
        )
    try:
        org_id = int(org_id)
    except (TypeError, ValueError):
        raise ValidationError({"org_id": "Must be an integer."})
    matched = [m for m in memberships if m.organization_id == org_id]
    if not matched:
        raise PermissionDenied("No active coach membership found in the specified organization.")
    return matched[0]


def _tsb_zone(tsb: float) -> str:
    if tsb >= 25:
        return "fresh"
    elif tsb >= 0:
        return "optimal"
    elif tsb >= -10:
        return "productive"
    elif tsb >= -30:
        return "fatigued"
    else:
        return "overreaching"


def _build_pmc_payload(daily_loads_qs, days: int) -> dict:
    """
    Build the PMC response dict from a DailyLoad queryset ordered by date.
    Computes a 'current' summary block from the most recent record.

    PR-153: adds ramp_rate_7d, ramp_rate_28d, and 14-day CTL projection.
    """
    rows = list(daily_loads_qs.order_by("date").values(
        "date", "tss", "ctl", "atl", "tsb", "ars"
    ))

    if rows:
        latest = rows[-1]
        latest_date = latest["date"]
        latest_ctl = latest["ctl"]
        zone = _tsb_zone(latest["tsb"])

        # Ramp rate: CTL change over 7d and 28d
        ctl_by_date = {r["date"]: r["ctl"] for r in rows}
        ctl_7d_ago = ctl_by_date.get(latest_date - timedelta(days=7), 0.0)
        ctl_28d_ago = ctl_by_date.get(latest_date - timedelta(days=28), 0.0)
        ramp_rate_7d = round(latest_ctl - ctl_7d_ago, 1)
        ramp_rate_28d = round((latest_ctl - ctl_28d_ago) / 4, 1)

        current = {
            "ctl": latest_ctl,
            "atl": latest["atl"],
            "tsb": latest["tsb"],
            "ars": latest["ars"],
            "ars_label": _TSB_ZONE_LABELS.get(zone, zone),
            "tsb_zone": zone,
            "ramp_rate_7d": ramp_rate_7d,
            "ramp_rate_28d": ramp_rate_28d,
        }

        # CTL projection: 14 days forward using current 7d ramp rate
        daily_ramp = ramp_rate_7d / 7.0
        projected_ctl = latest_ctl
        projection = []
        for i in range(1, 15):
            projected_ctl = projected_ctl + daily_ramp
            projection.append({
                "date": (latest_date + timedelta(days=i)).isoformat(),
                "ctl": round(projected_ctl, 1),
            })
    else:
        current = {
            "ctl": 0.0, "atl": 0.0, "tsb": 0.0,
            "ars": 50, "ars_label": "Sin datos", "tsb_zone": "optimal",
            "ramp_rate_7d": 0.0, "ramp_rate_28d": 0.0,
        }
        projection = []

    serialized_days = [
        {
            "date": r["date"].isoformat(),
            "tss": r["tss"],
            "ctl": r["ctl"],
            "atl": r["atl"],
            "tsb": r["tsb"],
            "ars": r["ars"],
        }
        for r in rows
    ]

    return {
        "current": current,
        "days": serialized_days,
        "period_days": days,
        "projection": projection,
    }


def _validate_days(request) -> int:
    """Parse and validate the `days` query param. Returns int in [1, 365]."""
    try:
        days = int(request.query_params.get("days", 90))
    except (TypeError, ValueError):
        raise ValidationError({"days": "Must be a positive integer."})
    if days < 1 or days > 365:
        raise ValidationError({"days": "Must be between 1 and 365."})
    return days


def _compute_readiness(athlete_user, org, current_tsb: float) -> tuple:
    """
    Compute a 0-100 readiness score combining load (TSB) and latest wellness check-in.

    Returns (score, label, recommendation).
    Returns (None, None, None) when neither wellness check-in nor activity load exists,
    so the UI can show an "add your first check-in" prompt instead of a misleading 50/100.
    """
    # Wellness component: latest check-in average (1-5) scaled to 0-100
    wellness_score = None  # None = no data yet
    has_checkin = False
    athlete_obj = Athlete.objects.filter(user=athlete_user, organization=org).first()
    if athlete_obj:
        checkin = (
            WellnessCheckIn.objects
            .filter(athlete=athlete_obj, organization=org)
            .order_by("-date")
            .first()
        )
        if checkin:
            has_checkin = True
            avg = (
                checkin.sleep_quality + checkin.mood + checkin.energy
                + checkin.muscle_soreness + checkin.stress
            ) / 5.0
            wellness_score = avg * 20.0  # scale 1-5 → 20-100

    # BUG-8 fix: TSB = 0.0 means no activities have been processed yet.
    has_load_data = bool(current_tsb)

    if not has_checkin and not has_load_data:
        # No data at all — return None so the UI shows an onboarding prompt.
        return None, None, None

    if wellness_score is None:
        wellness_score = 50.0  # neutral fallback when we have load but no wellness

    # Load component: map TSB from [-30, +30] → [0, 100]
    tsb_clamped = max(-30.0, min(30.0, float(current_tsb or 0)))
    load_score = ((tsb_clamped + 30) / 60) * 100

    score = int(round(wellness_score * 0.5 + load_score * 0.5))
    score = max(0, min(100, score))

    if score >= 75:
        label = "Listo para entrenar"
        recommendation = "Estás listo para entrenar fuerte. Aprovechá el día."
    elif score >= 50:
        label = "Entrenar con precaución"
        recommendation = "Podés entrenar con normalidad. Escuchá tu cuerpo."
    elif score >= 25:
        label = "Carga alta, moderar"
        recommendation = "Tu cuerpo necesita moderación. Entrenamiento suave hoy."
    else:
        label = "Recuperación recomendada"
        recommendation = "Recuperación recomendada. Descansá o hacé actividad muy liviana."

    return score, label, recommendation


# ==============================================================================
# Athlete endpoints
# ==============================================================================

class AthletePMCView(APIView):
    """
    GET /api/athlete/pmc/?days=90

    Returns the athlete's own PMC from DailyLoad (pre-computed by PMC engine).
    403 if the user is not an active athlete in any org.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = _get_athlete_membership(request)
        org = membership.organization
        days = _validate_days(request)

        today = timezone.now().date()
        from datetime import timedelta
        start_date = today - timedelta(days=days - 1)

        qs = DailyLoad.objects.filter(
            organization=org,
            athlete=request.user,
            date__gte=start_date,
            date__lte=today,
        )
        payload = _build_pmc_payload(qs, days)
        readiness_score, readiness_label, readiness_recommendation = _compute_readiness(
            request.user, org, payload["current"]["tsb"]
        )
        payload["current"]["readiness_score"] = readiness_score
        payload["current"]["readiness_label"] = readiness_label
        payload["current"]["readiness_recommendation"] = readiness_recommendation

        logger.info(
            "athlete_pmc_view.served",
            extra={
                "event_name": "athlete_pmc_view.served",
                "organization_id": org.pk,
                "user_id": request.user.pk,
                "days": days,
                "rows": len(payload["days"]),
                "outcome": "success",
            },
        )
        return Response(payload)


class AthleteHRProfileView(APIView):
    """
    GET  /api/athlete/hr-profile/ — retrieve own HR profile.
    PUT  /api/athlete/hr-profile/ — update own HR profile; triggers PMC full recompute.

    403 if the user is not an active athlete.
    """

    permission_classes = [IsAuthenticated]

    def _get_or_create_profile(self, user, org):
        profile, _ = AthleteHRProfile.objects.get_or_create(
            organization=org,
            athlete=user,
            defaults={"hr_max": 190, "hr_rest": 55},
        )
        return profile

    def get(self, request):
        membership = _get_athlete_membership(request)
        org = membership.organization
        profile = self._get_or_create_profile(request.user, org)
        return Response({
            "hr_max": profile.hr_max,
            "hr_rest": profile.hr_rest,
            "threshold_pace_s_km": profile.threshold_pace_s_km,
        })

    def put(self, request):
        membership = _get_athlete_membership(request)
        org = membership.organization
        profile = self._get_or_create_profile(request.user, org)

        # Validate fields
        serializer = _HRProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        profile.hr_max = data.get("hr_max", profile.hr_max)
        profile.hr_rest = data.get("hr_rest", profile.hr_rest)
        profile.threshold_pace_s_km = data.get("threshold_pace_s_km", profile.threshold_pace_s_km)
        profile.save(update_fields=["hr_max", "hr_rest", "threshold_pace_s_km", "updated_at"])

        # Trigger full PMC recompute in background (non-blocking)
        try:
            from core.tasks import compute_pmc_full_for_athlete
            compute_pmc_full_for_athlete.delay(request.user.pk, org.pk)
        except Exception:
            logger.warning(
                "hr_profile_update.pmc_dispatch_failed",
                extra={
                    "event_name": "hr_profile_update.pmc_dispatch_failed",
                    "organization_id": org.pk,
                    "user_id": request.user.pk,
                },
            )

        logger.info(
            "hr_profile_updated",
            extra={
                "event_name": "hr_profile_updated",
                "organization_id": org.pk,
                "user_id": request.user.pk,
                "outcome": "success",
            },
        )
        return Response({
            "hr_max": profile.hr_max,
            "hr_rest": profile.hr_rest,
            "threshold_pace_s_km": profile.threshold_pace_s_km,
        })


class _HRProfileSerializer(serializers.Serializer):
    hr_max = serializers.IntegerField(min_value=100, max_value=250, required=False)
    hr_rest = serializers.IntegerField(min_value=20, max_value=100, required=False)
    threshold_pace_s_km = serializers.FloatField(min_value=60.0, max_value=1800.0, required=False, allow_null=True)


# ==============================================================================
# Coach endpoints
# ==============================================================================

class CoachAthletePMCView(APIView):
    """
    GET /api/coach/athletes/<membership_id>/pmc/?days=90

    Returns any athlete's PMC within the coach's org.
    membership_id is the athlete's Membership PK — validated to belong to
    the same org as the authenticated coach (fail-closed 404).
    403 if the user is not an active coach/owner.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, membership_id: int):
        coach_membership = _get_coach_membership(request)
        org = coach_membership.organization

        # Resolve athlete membership — fail-closed: must belong to coach's org
        try:
            athlete_membership = Membership.objects.select_related("user").get(
                pk=membership_id,
                organization=org,
                role=Membership.Role.ATHLETE,
                is_active=True,
            )
        except Membership.DoesNotExist:
            raise NotFound("Athlete membership not found in this organization.")

        athlete_user = athlete_membership.user
        days = _validate_days(request)

        today = timezone.now().date()
        from datetime import timedelta
        start_date = today - timedelta(days=days - 1)

        qs = DailyLoad.objects.filter(
            organization=org,
            athlete=athlete_user,
            date__gte=start_date,
            date__lte=today,
        )
        payload = _build_pmc_payload(qs, days)
        readiness_score, readiness_label, readiness_recommendation = _compute_readiness(
            athlete_user, org, payload["current"]["tsb"]
        )
        payload["current"]["readiness_score"] = readiness_score
        payload["current"]["readiness_label"] = readiness_label
        payload["current"]["readiness_recommendation"] = readiness_recommendation
        payload["athlete_name"] = (
            athlete_user.get_full_name() or athlete_user.username
        )

        logger.info(
            "coach_athlete_pmc_view.served",
            extra={
                "event_name": "coach_athlete_pmc_view.served",
                "organization_id": org.pk,
                "coach_user_id": request.user.pk,
                "athlete_user_id": athlete_user.pk,
                "days": days,
                "outcome": "success",
            },
        )
        return Response(payload)


def _strava_health(identity_status, has_deferred: bool) -> str:
    from core.models import ExternalIdentity as _EI
    if identity_status == _EI.Status.LINKED:
        return "deferred" if has_deferred else "healthy"
    return "disconnected"


class TeamReadinessView(APIView):
    """
    GET /api/coach/team-readiness/

    Returns today's TSB zone summary for all athletes in the coach's org.
    Uses the latest DailyLoad record per athlete.
    403 if the user is not an active coach/owner.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        coach_membership = _get_coach_membership(request)
        org = coach_membership.organization

        today = timezone.now().date()

        # A.1 — coach-scoped filter: coaches only see their assigned athletes.
        if coach_membership.role == Membership.Role.COACH:
            coach_obj = Coach.objects.filter(user=request.user, organization=org).first()
            if coach_obj:
                assigned_pks = set(
                    AthleteCoachAssignment.objects.filter(
                        organization=org, coach=coach_obj, ended_at__isnull=True
                    ).values_list("athlete_id", flat=True)
                )
                assigned_user_ids = set(
                    Athlete.objects.filter(pk__in=assigned_pks).values_list("user_id", flat=True)
                )
            else:
                assigned_user_ids = set()
            athlete_memberships = (
                Membership.objects.select_related("user")
                .filter(organization=org, role=Membership.Role.ATHLETE, is_active=True,
                        user_id__in=assigned_user_ids)
            )
        else:
            # Get all active athlete memberships in this org (owner/admin sees all)
            athlete_memberships = (
                Membership.objects.select_related("user")
                .filter(organization=org, role=Membership.Role.ATHLETE, is_active=True)
            )

        # Get latest DailyLoad for each athlete (use today's or most recent)
        summary = {
            "overreaching": 0,
            "fatigued": 0,
            "productive": 0,
            "optimal": 0,
            "fresh": 0,
        }
        athletes_data = []

        athlete_user_ids = [m.user_id for m in athlete_memberships]
        membership_by_user = {m.user_id: m for m in athlete_memberships}

        # Fetch the most recent DailyLoad per athlete (not just today)
        from django.db.models import Max

        latest_date_by_user = dict(
            DailyLoad.objects.filter(
                organization=org,
                athlete_id__in=athlete_user_ids,
            )
            .values("athlete_id")
            .annotate(latest=Max("date"))
            .values_list("athlete_id", "latest")
        )

        load_by_user: dict = {}
        for user_id, latest_date in latest_date_by_user.items():
            dl = (
                DailyLoad.objects.filter(
                    organization=org,
                    athlete_id=user_id,
                    date=latest_date,
                )
                .select_related("athlete")
                .first()
            )
            if dl:
                load_by_user[user_id] = dl

        # Ramp rate: 7 days before each athlete's latest DailyLoad date
        load_7d_ago: dict = {}
        for user_id, latest_date in latest_date_by_user.items():
            ref_date = latest_date - timedelta(days=7)
            dl7 = DailyLoad.objects.filter(
                organization=org,
                athlete_id=user_id,
                date=ref_date,
            ).values_list("ctl", flat=True).first()
            if dl7 is not None:
                load_7d_ago[user_id] = dl7

        # Resolve Alumnos for all athletes in one batch (Alumno = legacy ingestion FK)
        from core.models import Alumno as _Alumno
        alumnos_qs = _Alumno.objects.filter(usuario_id__in=athlete_user_ids).values("pk", "usuario_id")
        user_to_alumno_id = {row["usuario_id"]: row["pk"] for row in alumnos_qs}
        alumno_ids = list(user_to_alumno_id.values())

        # Strava sync health — two batch queries
        from core.models import ExternalIdentity, StravaWebhookEvent
        identity_by_alumno = {
            row["alumno_id"]: row["status"]
            for row in ExternalIdentity.objects.filter(
                provider="strava", alumno_id__in=alumno_ids
            ).values("alumno_id", "status")
        }
        deferred_alumno_ids = set(
            ExternalIdentity.objects.filter(
                provider="strava",
                alumno_id__in=alumno_ids,
                status=ExternalIdentity.Status.LINKED,
            ).filter(
                alumno__strava_athlete_id__in=list(
                    StravaWebhookEvent.objects.filter(
                        status=StravaWebhookEvent.Status.LINK_REQUIRED
                    ).values_list("owner_id", flat=True)
                )
            ).values_list("alumno_id", flat=True)
        )

        # Weekly compliance — uses Athlete (P1), not Alumno
        week_start = today - timedelta(days=today.weekday())
        user_to_athlete_id = dict(
            Athlete.objects.filter(user_id__in=athlete_user_ids, organization=org)
            .values_list("user_id", "id")
        )
        athlete_pks = list(user_to_athlete_id.values())
        wa_this_week = list(
            WorkoutAssignment.objects.filter(
                organization=org,
                scheduled_date__gte=week_start,
                scheduled_date__lte=today,
                athlete_id__in=athlete_pks,
            ).values(
                "athlete_id",
                "actual_distance_meters",
                "planned_workout__estimated_distance_meters",
                "compliance_color",
            )
        )
        compliance_by_user: dict = {}
        for uid, ath_pk in user_to_athlete_id.items():
            rows = [r for r in wa_this_week if r["athlete_id"] == ath_pk]
            pcts = []
            for r in rows:
                pw_dist = r["planned_workout__estimated_distance_meters"]
                ac_dist = r["actual_distance_meters"]
                if pw_dist and ac_dist and pw_dist > 0:
                    pcts.append(min(round(ac_dist / pw_dist * 100), 200))
                elif r["compliance_color"] == "green":
                    pcts.append(100)
            compliance_by_user[uid] = round(sum(pcts) / len(pcts)) if pcts else None

        # GAP: last 7 days of run/trail activities — batched per alumno
        seven_ago_dt = today - timedelta(days=7)
        run_sports = ["RUN", "TRAIL"]
        gap_by_user: dict = {}
        for m in athlete_memberships:
            alumno_id = user_to_alumno_id.get(m.user_id)
            if not alumno_id:
                continue
            agg = CompletedActivity.objects.filter(
                organization=org,
                alumno_id=alumno_id,
                sport__in=run_sports,
                start_time__date__gte=seven_ago_dt,
                start_time__date__lte=today,
                deleted_at__isnull=True,
            ).aggregate(
                td=Sum("distance_m", output_field=FloatField()),
                te=Sum("elevation_gain_m", output_field=FloatField()),
                ts=Sum("duration_s", output_field=FloatField()),
            )
            gap = compute_gap(agg["td"] or 0, agg["te"] or 0, agg["ts"] or 0)
            if gap is not None:
                gap_by_user[m.user_id] = _fmt_gap_pace(gap)

        # Last activity date per alumno — one batch query
        last_act_rows = (
            CompletedActivity.objects.filter(
                organization=org,
                alumno_id__in=alumno_ids,
                deleted_at__isnull=True,
            )
            .values("alumno_id")
            .annotate(last_start=Max("start_time"))
        )
        last_act_by_alumno: dict = {}
        for row in last_act_rows:
            if row["last_start"]:
                last_act_by_alumno[row["alumno_id"]] = row["last_start"].date()

        for membership in athlete_memberships:
            user_id = membership.user_id
            dl = load_by_user.get(user_id)

            if dl:
                tsb = dl.tsb
                ctl = dl.ctl
                atl = dl.atl
                ars = dl.ars
            else:
                tsb = 0.0
                ctl = 0.0
                atl = 0.0
                ars = 50

            ctl_7d_ago = load_7d_ago.get(user_id, 0.0)
            ramp_rate_7d = round(ctl - ctl_7d_ago, 1)

            alumno_id = user_to_alumno_id.get(user_id)
            last_act_date = last_act_by_alumno.get(alumno_id) if alumno_id else None
            last_activity_days_ago = (today - last_act_date).days if last_act_date else None

            zone = _tsb_zone(tsb)
            if zone in summary:
                summary[zone] += 1

            athletes_data.append({
                "membership_id": membership.pk,
                "name": membership.user.get_full_name() or membership.user.username,
                "ctl": ctl,
                "atl": atl,
                "tsb": tsb,
                "ars": ars,
                "tsb_zone": zone,
                "ramp_rate_7d": ramp_rate_7d,
                "avg_gap_formatted": gap_by_user.get(user_id, "—"),
                "last_activity_days_ago": last_activity_days_ago,
                "strava_sync_health": _strava_health(
                    identity_by_alumno.get(alumno_id),
                    alumno_id in deferred_alumno_ids,
                ),
                "compliance_pct_this_week": compliance_by_user.get(user_id),
            })

        logger.info(
            "team_readiness_view.served",
            extra={
                "event_name": "team_readiness_view.served",
                "organization_id": org.pk,
                "coach_user_id": request.user.pk,
                "athlete_count": len(athletes_data),
                "outcome": "success",
            },
        )
        return Response({"summary": summary, "athletes": athletes_data})


# ==============================================================================
# Pace Zones — PR-145a
# ==============================================================================

def _fmt_pace(s_km: float) -> str:
    """Convert seconds/km to 'M:SS/km' display string."""
    s_km = int(round(s_km))
    return f"{s_km // 60}:{s_km % 60:02d}/km"


class PaceZonesView(APIView):
    """
    GET /api/athlete/pace-zones/

    Returns Z1-Z5 pace zones derived from the authenticated user's
    threshold pace (AthleteHRProfile.threshold_pace_s_km).
    Falls back to 300 s/km (5:00/km) when no profile exists.

    Available to any user with an active Membership (athlete or coach),
    because coaches also need pace zone reference when building workouts.
    Tenancy: org is resolved from the user's active Membership — never
    from request params.
    """

    permission_classes = [IsAuthenticated]

    _ZONE_DEFS = [
        # (key, name, min_mult, max_mult, color, description)
        ("Z1", "Recuperación", 1.40, 1.60, "#94a3b8", "Muy fácil, conversación fluida"),
        ("Z2", "Aeróbico",     1.20, 1.39, "#22c55e", "Cómodo, base aeróbica"),
        ("Z3", "Tempo",        1.06, 1.19, "#eab308", "Moderado-fuerte, controlable"),
        ("Z4", "Umbral",       0.98, 1.05, "#f97316", "Difícil, máximo sostenible"),
        ("Z5", "VO2max",       0.85, 0.97, "#ef4444", "Muy intenso, series cortas"),
    ]

    def get(self, request):
        membership = (
            Membership.objects
            .select_related("organization")
            .filter(user=request.user, is_active=True)
            .first()
        )
        if not membership:
            raise PermissionDenied("No active membership found.")

        org = membership.organization

        hr_profile = AthleteHRProfile.objects.filter(
            athlete=request.user,
            organization=org,
        ).first()

        has_threshold = (
            hr_profile is not None
            and hr_profile.threshold_pace_s_km is not None
        )
        threshold_s = float(hr_profile.threshold_pace_s_km) if has_threshold else 300.0

        zones = {}
        for key, name, min_mult, max_mult, color, desc in self._ZONE_DEFS:
            zones[key] = {
                "name": name,
                "pace_min": _fmt_pace(threshold_s * min_mult),
                "pace_max": _fmt_pace(threshold_s * max_mult),
                "pace_min_s": round(threshold_s * min_mult, 1),
                "pace_max_s": round(threshold_s * max_mult, 1),
                "color": color,
                "description": desc,
            }

        logger.info(
            "pace_zones_calculated",
            extra={
                "event_name": "pace_zones_calculated",
                "user_id": request.user.pk,
                "organization_id": org.pk,
                "has_threshold": has_threshold,
                "outcome": "success",
            },
        )

        return Response({
            "has_threshold": has_threshold,
            "threshold_pace_s_km": threshold_s,
            "threshold_pace_display": _fmt_pace(threshold_s),
            "zones": zones,
        })


# ==============================================================================
# PR-152: Training Volume, Wellness History, Compliance
# All three use the same membership_id resolution pattern as CoachAthletePMCView.
# ==============================================================================

_SPORT_FILTERS = {
    "run": ["RUN", "TRAIL"],
    "cycling": ["CYCLING", "MTB", "INDOOR_BIKE"],
    "strength": ["STRENGTH"],
    "all": None,
}

_METRIC_FIELDS = {
    "distance": "distance_m",
    "duration": "duration_s",
    "elevation": "elevation_gain_m",
    "load": "canonical_load",
}


def _resolve_athlete_membership(request, membership_id: int):
    """
    Validate membership_id belongs to an athlete in the coach's org.
    Returns (coach_org, athlete_membership, athlete_user).
    Fail-closed: raises NotFound if the membership doesn't exist in the coach's org.
    """
    coach_membership = _get_coach_membership(request)
    org = coach_membership.organization
    try:
        athlete_membership = Membership.objects.select_related("user").get(
            pk=membership_id,
            organization=org,
            role=Membership.Role.ATHLETE,
            is_active=True,
        )
    except Membership.DoesNotExist:
        raise NotFound("Athlete membership not found in this organization.")
    return org, athlete_membership, athlete_membership.user


def _period_buckets_from_qs(qs, date_field: str, value_field: str, precision: str) -> list:
    """
    Group a queryset by week or month, returning a list of bucket dicts.
    date_field: name of the DateTimeField or DateField to truncate.
    value_field: annotated Sum field name.
    precision: 'weekly' | 'monthly'
    """
    trunc_fn = TruncWeek if precision == "weekly" else TruncMonth
    rows = (
        qs
        .annotate(period=trunc_fn(date_field))
        .values("period")
        .annotate(value=Sum(value_field, output_field=FloatField()), sessions=Count("id"))
        .order_by("period")
    )
    buckets = []
    for row in rows:
        period_start = row["period"]
        if hasattr(period_start, "date"):
            period_start = period_start.date()
        if precision == "weekly":
            period_end = period_start + timedelta(days=6)
        else:
            # last day of month
            if period_start.month == 12:
                period_end = period_start.replace(day=31)
            else:
                period_end = (
                    period_start.replace(month=period_start.month + 1, day=1)
                    - timedelta(days=1)
                )
        buckets.append({
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "value": round(float(row["value"] or 0), 2),
            "sessions": row["sessions"],
        })
    return buckets


class TrainingVolumeView(APIView):
    """
    GET /api/coach/athletes/<membership_id>/training-volume/

    Query params:
        metric:    distance | duration | elevation | load  (default: distance)
        sport:     all | run | cycling | strength          (default: all)
        precision: weekly | monthly                        (default: weekly)
        days:      1–365                                   (default: 90)

    Returns aggregated training volume buckets for the athlete.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, membership_id: int):
        org, athlete_membership, athlete_user = _resolve_athlete_membership(
            request, membership_id
        )
        days = _validate_days(request)

        metric = request.query_params.get("metric", "distance")
        sport = request.query_params.get("sport", "all")
        precision = request.query_params.get("precision", "weekly")

        if metric not in _METRIC_FIELDS:
            raise ValidationError({"metric": f"Must be one of: {list(_METRIC_FIELDS.keys())}"})
        if sport not in _SPORT_FILTERS:
            raise ValidationError({"sport": f"Must be one of: {list(_SPORT_FILTERS.keys())}"})
        if precision not in ("weekly", "monthly"):
            raise ValidationError({"precision": "Must be 'weekly' or 'monthly'."})

        today = timezone.now().date()
        start_date = today - timedelta(days=days - 1)

        # Resolve alumno (legacy path — most activities ingested via Alumno FK)
        alumno = Alumno.objects.filter(usuario=athlete_user).first()
        if not alumno:
            return Response({
                "metric": metric, "sport": sport, "precision": precision,
                "summary": {"total": 0, "average_per_period": 0, "count_sessions": 0, "planned_total": None},
                "buckets": [],
            })

        metric_field = _METRIC_FIELDS[metric]
        sport_list = _SPORT_FILTERS[sport]
        is_run_sport = sport in ("run",)  # run includes TRAIL via _SPORT_FILTERS

        qs = CompletedActivity.objects.filter(
            organization=org,
            alumno=alumno,
            start_time__date__gte=start_date,
            start_time__date__lte=today,
            deleted_at__isnull=True,
        )
        if sport_list:
            qs = qs.filter(sport__in=sport_list)

        # Enhanced aggregation: include elevation + distance + duration for GAP
        trunc_fn = TruncWeek if precision == "weekly" else TruncMonth
        raw_rows = (
            qs
            .annotate(period=trunc_fn("start_time"))
            .values("period")
            .annotate(
                value=Sum(metric_field, output_field=FloatField()),
                sessions=Count("id"),
                total_distance_m=Sum("distance_m", output_field=FloatField()),
                total_elevation_gain_m=Sum("elevation_gain_m", output_field=FloatField()),
                total_duration_s=Sum("duration_s", output_field=FloatField()),
            )
            .order_by("period")
        )

        buckets = []
        for row in raw_rows:
            period_start = row["period"]
            if hasattr(period_start, "date"):
                period_start = period_start.date()
            if precision == "weekly":
                period_end = period_start + timedelta(days=6)
            else:
                if period_start.month == 12:
                    period_end = period_start.replace(day=31)
                else:
                    period_end = (
                        period_start.replace(month=period_start.month + 1, day=1)
                        - timedelta(days=1)
                    )

            elev_gain = float(row["total_elevation_gain_m"] or 0)
            dist_m = float(row["total_distance_m"] or 0)
            dur_s = float(row["total_duration_s"] or 0)

            bucket = {
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "value": round(float(row["value"] or 0), 2),
                "sessions": row["sessions"],
                "elevation_gain_m": round(elev_gain, 1),
            }

            # GAP: computed on-the-fly for run/trail
            if is_run_sport and dist_m > 0 and dur_s > 0:
                gap = compute_gap(dist_m, elev_gain, dur_s)
                if gap is not None:
                    bucket["avg_gap_s_km"] = gap
                    bucket["avg_gap_formatted"] = _fmt_gap_pace(gap)

            buckets.append(bucket)

        total = sum(b["value"] for b in buckets)
        count_sessions = sum(b["sessions"] for b in buckets)
        avg = round(total / len(buckets), 2) if buckets else 0

        # Summary-level GAP: aggregate across all buckets
        summary = {
            "total": total,
            "average_per_period": avg,
            "count_sessions": count_sessions,
            "planned_total": None,
            "total_elevation_gain_m": round(sum(b["elevation_gain_m"] for b in buckets), 1),
            # calories_kcal is not yet stored on CompletedActivity — placeholder for future
            "total_calories_kcal": None,
        }
        if is_run_sport:
            # Full-period GAP from totals across all activities
            agg = qs.aggregate(
                td=Sum("distance_m", output_field=FloatField()),
                te=Sum("elevation_gain_m", output_field=FloatField()),
                ts=Sum("duration_s", output_field=FloatField()),
            )
            overall_gap = compute_gap(
                agg["td"] or 0, agg["te"] or 0, agg["ts"] or 0
            )
            if overall_gap is not None:
                summary["avg_gap_s_km"] = overall_gap
                summary["avg_gap_formatted"] = _fmt_gap_pace(overall_gap)

        logger.info(
            "training_volume_view.served",
            extra={
                "event_name": "training_volume_view.served",
                "organization_id": org.pk,
                "coach_user_id": request.user.pk,
                "athlete_user_id": athlete_user.pk,
                "metric": metric, "sport": sport, "precision": precision, "days": days,
                "outcome": "success",
            },
        )
        return Response({
            "metric": metric,
            "sport": sport,
            "precision": precision,
            "summary": summary,
            "buckets": buckets,
        })


class WellnessHistoryView(APIView):
    """
    GET /api/coach/athletes/<membership_id>/wellness/?days=30

    Returns wellness check-in history for the athlete.
    Fields: date, sleep_quality, mood, energy, muscle_soreness, stress, average.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, membership_id: int):
        org, athlete_membership, athlete_user = _resolve_athlete_membership(
            request, membership_id
        )
        days = _validate_days(request)

        today = timezone.now().date()
        start_date = today - timedelta(days=days - 1)

        # WellnessCheckIn uses Athlete FK (new org-first model)
        athlete_obj = Athlete.objects.filter(user=athlete_user, organization=org).first()
        if not athlete_obj:
            return Response({
                "athlete_name": athlete_user.get_full_name() or athlete_user.username,
                "entries": [],
                "period_average": None,
            })

        checkins = (
            WellnessCheckIn.objects
            .filter(athlete=athlete_obj, organization=org, date__gte=start_date, date__lte=today)
            .order_by("date")
            .values("date", "sleep_quality", "mood", "energy", "muscle_soreness", "stress")
        )

        entries = []
        for c in checkins:
            avg = (c["sleep_quality"] + c["mood"] + c["energy"]
                   + c["muscle_soreness"] + c["stress"]) / 5.0
            entries.append({
                "date": c["date"].isoformat(),
                "sleep": c["sleep_quality"],
                "mood": c["mood"],
                "energy": c["energy"],
                "soreness": c["muscle_soreness"],
                "stress": c["stress"],
                "average": round(avg, 2),
            })

        period_avg = round(sum(e["average"] for e in entries) / len(entries), 2) if entries else None

        logger.info(
            "wellness_history_view.served",
            extra={
                "event_name": "wellness_history_view.served",
                "organization_id": org.pk,
                "coach_user_id": request.user.pk,
                "athlete_user_id": athlete_user.pk,
                "entries": len(entries),
                "outcome": "success",
            },
        )
        return Response({
            "athlete_name": athlete_user.get_full_name() or athlete_user.username,
            "entries": entries,
            "period_average": period_avg,
        })


class ComplianceView(APIView):
    """
    GET /api/coach/athletes/<membership_id>/compliance/?days=30&precision=weekly

    Returns plan compliance buckets: planned sessions vs completed sessions.
    Compliance % = completed / total_non_canceled * 100 per period.
    Returns "no plan" message when no WorkoutAssignments exist.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, membership_id: int):
        org, athlete_membership, athlete_user = _resolve_athlete_membership(
            request, membership_id
        )
        days = _validate_days(request)
        precision = request.query_params.get("precision", "weekly")
        if precision not in ("weekly", "monthly"):
            raise ValidationError({"precision": "Must be 'weekly' or 'monthly'."})

        today = timezone.now().date()
        start_date = today - timedelta(days=days - 1)

        # WorkoutAssignment uses Athlete FK
        athlete_obj = Athlete.objects.filter(user=athlete_user, organization=org).first()
        if not athlete_obj:
            return Response({
                "overall_pct": None,
                "buckets": [],
                "message": "No hay plan asignado",
            })

        base_qs = WorkoutAssignment.objects.filter(
            organization=org,
            athlete=athlete_obj,
            scheduled_date__gte=start_date,
            scheduled_date__lte=today,
        ).exclude(status=WorkoutAssignment.Status.CANCELED)

        if not base_qs.exists():
            return Response({
                "overall_pct": None,
                "buckets": [],
                "message": "No hay plan asignado",
            })

        trunc_fn = TruncWeek if precision == "weekly" else TruncMonth

        rows = (
            base_qs
            .annotate(period=trunc_fn("scheduled_date"))
            .values("period")
            .annotate(
                planned_sessions=Count("id"),
                completed_sessions=Count(
                    "id",
                    filter=Q(status=WorkoutAssignment.Status.COMPLETED),
                ),
            )
            .order_by("period")
        )

        buckets = []
        total_planned = 0
        total_completed = 0
        for row in rows:
            period_start = row["period"]
            if hasattr(period_start, "date"):
                period_start = period_start.date()
            if precision == "weekly":
                period_end = period_start + timedelta(days=6)
            else:
                if period_start.month == 12:
                    period_end = period_start.replace(day=31)
                else:
                    period_end = (
                        period_start.replace(month=period_start.month + 1, day=1)
                        - timedelta(days=1)
                    )
            planned = row["planned_sessions"]
            completed = row["completed_sessions"]
            pct = round(completed / planned * 100) if planned else 0
            total_planned += planned
            total_completed += completed
            buckets.append({
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "planned_sessions": planned,
                "actual_sessions": completed,
                "compliance_pct": pct,
            })

        overall_pct = round(total_completed / total_planned * 100) if total_planned else None

        logger.info(
            "compliance_view.served",
            extra={
                "event_name": "compliance_view.served",
                "organization_id": org.pk,
                "coach_user_id": request.user.pk,
                "athlete_user_id": athlete_user.pk,
                "precision": precision, "days": days,
                "outcome": "success",
            },
        )
        return Response({
            "overall_pct": overall_pct,
            "buckets": buckets,
        })
