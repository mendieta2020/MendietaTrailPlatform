"""
core/views_pmc.py

PMC (Performance Management Chart) API views — PR-128a.

Endpoints:
    GET  /api/athlete/pmc/               — athlete reads own PMC from DailyLoad
    GET  /api/coach/athletes/<m_id>/pmc/ — coach reads any athlete's PMC
    GET  /api/coach/team-readiness/      — coach reads team TSB summary
    GET  /api/athlete/hr-profile/        — athlete reads own HR profile
    PUT  /api/athlete/hr-profile/        — athlete updates own HR profile

Tenancy: organization is always resolved from the authenticated user's active
Membership — never from request body or query params.
Law 6: no PII logged (user IDs only, no names/emails).
"""
import logging

from django.utils import timezone

from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import AthleteHRProfile, DailyLoad, Membership

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
    Returns the Membership instance or raises 403.
    """
    try:
        membership = Membership.objects.select_related("organization").get(
            user=request.user,
            is_active=True,
        )
    except Membership.DoesNotExist:
        raise PermissionDenied("No active membership found.")
    if membership.role != Membership.Role.ATHLETE:
        raise PermissionDenied("Only athletes can access this endpoint.")
    return membership


def _get_coach_membership(request):
    """
    Resolve the requesting user's active coach/owner Membership.
    Returns the Membership instance or raises 403.
    """
    try:
        membership = Membership.objects.select_related("organization").get(
            user=request.user,
            is_active=True,
        )
    except Membership.DoesNotExist:
        raise PermissionDenied("No active membership found.")
    if membership.role not in _COACH_ROLES:
        raise PermissionDenied("Only coaches and owners can access this endpoint.")
    return membership


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
    """
    from core.services_pmc import compute_ars

    rows = list(daily_loads_qs.order_by("date").values(
        "date", "tss", "ctl", "atl", "tsb", "ars"
    ))

    if rows:
        latest = rows[-1]
        zone = _tsb_zone(latest["tsb"])
        current = {
            "ctl": latest["ctl"],
            "atl": latest["atl"],
            "tsb": latest["tsb"],
            "ars": latest["ars"],
            "ars_label": _TSB_ZONE_LABELS.get(zone, zone),
            "tsb_zone": zone,
        }
    else:
        current = {
            "ctl": 0.0, "atl": 0.0, "tsb": 0.0,
            "ars": 50, "ars_label": "Sin datos", "tsb_zone": "optimal",
        }

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

    return {"current": current, "days": serialized_days, "period_days": days}


def _validate_days(request) -> int:
    """Parse and validate the `days` query param. Returns int in [1, 365]."""
    try:
        days = int(request.query_params.get("days", 90))
    except (TypeError, ValueError):
        raise ValidationError({"days": "Must be a positive integer."})
    if days < 1 or days > 365:
        raise ValidationError({"days": "Must be between 1 and 365."})
    return days


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

        # Get all active athlete memberships in this org
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

        # Fetch today's DailyLoad for all athletes in one query
        daily_loads = DailyLoad.objects.filter(
            organization=org,
            athlete_id__in=athlete_user_ids,
            date=today,
        ).select_related("athlete")

        load_by_user = {dl.athlete_id: dl for dl in daily_loads}

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

            zone = _tsb_zone(tsb)
            if zone in summary:
                summary[zone] += 1

            athletes_data.append({
                "membership_id": membership.pk,
                "ctl": ctl,
                "atl": atl,
                "tsb": tsb,
                "ars": ars,
                "tsb_zone": zone,
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
