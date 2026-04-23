"""
core/views_reports.py — PR-154

Shareable athlete training reports: coach generates a token-protected URL,
athlete opens a public page (no login required) with their training summary.

Endpoints (authenticated, coach-only):
  POST /api/coach/athletes/<membership_id>/report/
  POST /api/coach/athletes/<membership_id>/report/<token>/email/

Endpoints (public, no auth):
  GET  /report/<token>/

Tenancy: all access validated via Membership.  Token expires in 7 days.
Law 6: no PII logged (user IDs only, no names/emails).
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from django.core.mail import send_mail
from django.db.models import Avg, Count, FloatField, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import (
    Athlete,
    AthleteReport,
    CompletedActivity,
    DailyLoad,
    Membership,
    WellnessCheckIn,
    WorkoutAssignment,
)
from core.services_gap import compute_gap, format_pace as _fmt_gap_pace
from core.views_pmc import (
    _build_pmc_payload,
    _compute_readiness,
    _get_coach_membership,
    _resolve_athlete_membership,
)

logger = logging.getLogger(__name__)

_REPORT_TTL_DAYS = 7

_SPORT_VOLUME_MAP = {
    "TRAIL": ["TRAIL"],
    "RUN": ["RUN"],
    "CYCLING": ["CYCLING", "MTB", "INDOOR_BIKE"],
    "STRENGTH": ["STRENGTH"],
    "OTHER": ["SWIMMING", "CARDIO", "OTHER"],
}


def _build_volume_snapshot(org, athlete_user, alumno, start_date, today):
    """
    Return per-sport volume totals for the report period.
    Uses CompletedActivity (org-scoped, alumno FK).
    """
    if not alumno:
        return {}

    qs = CompletedActivity.objects.filter(
        organization=org,
        alumno=alumno,
        start_time__date__gte=start_date,
        start_time__date__lte=today,
        deleted_at__isnull=True,
    )

    rows = (
        qs.values("sport")
        .annotate(
            distance_m=Sum("distance_m", output_field=FloatField()),
            duration_s=Sum("duration_s", output_field=FloatField()),
            elevation_gain_m=Sum("elevation_gain_m", output_field=FloatField()),
            sessions_count=Count("id"),
        )
    )

    # Bucket by business sport group
    sport_totals: dict[str, dict] = {}
    for r in rows:
        raw = (r["sport"] or "OTHER").upper()
        group = "OTHER"
        for g, sports in _SPORT_VOLUME_MAP.items():
            if raw in sports:
                group = g
                break

        if group not in sport_totals:
            sport_totals[group] = {
                "distance_km": 0.0,
                "duration_minutes": 0,
                "elevation_gain_m": 0,
                "calories_kcal": 0,
                "sessions_count": 0,
            }
        t = sport_totals[group]
        t["distance_km"] += round((r["distance_m"] or 0) / 1000.0, 2)
        t["duration_minutes"] += int(round((r["duration_s"] or 0) / 60.0))
        t["elevation_gain_m"] += int(round(r["elevation_gain_m"] or 0))
        t["sessions_count"] += int(r["sessions_count"] or 0)

    # Extract calories from raw_payload (Strava sends 'calories' in the payload).
    # Grouped by the same sport bucketing so totals align.
    for act in qs.only("sport", "raw_payload"):
        cal = 0
        if act.raw_payload and isinstance(act.raw_payload, dict):
            cal = int(act.raw_payload.get("calories", 0) or 0)
        if cal > 0:
            raw = (act.sport or "OTHER").upper()
            group = "OTHER"
            for g, sports in _SPORT_VOLUME_MAP.items():
                if raw in sports:
                    group = g
                    break
            if group in sport_totals:
                sport_totals[group]["calories_kcal"] += cal

    # Round distance_km
    for v in sport_totals.values():
        v["distance_km"] = round(v["distance_km"], 2)

    return sport_totals


def _build_compliance_snapshot(org, athlete_user, start_date, today):
    """Return overall compliance percentage, or None if no plan."""
    athlete_obj = Athlete.objects.filter(user=athlete_user, organization=org).first()
    if not athlete_obj:
        return None

    base_qs = WorkoutAssignment.objects.filter(
        organization=org,
        athlete=athlete_obj,
        scheduled_date__gte=start_date,
        scheduled_date__lte=today,
    ).exclude(status=WorkoutAssignment.Status.CANCELED)

    agg = base_qs.aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status=WorkoutAssignment.Status.COMPLETED)),
    )
    if not agg["total"]:
        return None
    return round(agg["completed"] / agg["total"] * 100)


def _build_wellness_snapshot(org, athlete_user, start_date, today):
    """Return period average wellness score (1-5), or None."""
    athlete_obj = Athlete.objects.filter(user=athlete_user, organization=org).first()
    if not athlete_obj:
        return None

    checkins = WellnessCheckIn.objects.filter(
        athlete=athlete_obj,
        organization=org,
        date__gte=start_date,
        date__lte=today,
    ).values("sleep_quality", "mood", "energy", "muscle_soreness", "stress")

    if not checkins:
        return None

    averages = [
        (c["sleep_quality"] + c["mood"] + c["energy"]
         + c["muscle_soreness"] + c["stress"]) / 5.0
        for c in checkins
    ]
    return round(sum(averages) / len(averages), 2)


def _build_gap_snapshot(org, alumno, start_date, today):
    """Return overall GAP (Graded Adjusted Pace) for run/trail, or None."""
    if not alumno:
        return None

    agg = CompletedActivity.objects.filter(
        organization=org,
        alumno=alumno,
        sport__in=["RUN", "TRAIL"],
        start_time__date__gte=start_date,
        start_time__date__lte=today,
        deleted_at__isnull=True,
    ).aggregate(
        td=Sum("distance_m", output_field=FloatField()),
        te=Sum("elevation_gain_m", output_field=FloatField()),
        ts=Sum("duration_s", output_field=FloatField()),
    )
    gap = compute_gap(agg["td"] or 0, agg["te"] or 0, agg["ts"] or 0)
    return _fmt_gap_pace(gap) if gap is not None else None


def _build_narratives(ramp_rate_7d, acwr, compliance_pct, readiness_score):
    """
    Auto-generated text recommendations based on current training metrics.
    Returns a list of strings, each starting with a colored emoji indicator.
    """
    narratives = []

    # Fitness trend
    if ramp_rate_7d > 8:
        narratives.append(
            f"⚠️ Tu fitness está subiendo muy rápido (+{ramp_rate_7d:.1f}/sem). "
            "Moderar la carga para evitar sobreentrenamiento."
        )
    elif ramp_rate_7d > 3:
        narratives.append(
            f"↗️ Tu fitness está creciendo de forma saludable (+{ramp_rate_7d:.1f} CTL/semana)."
        )
    elif ramp_rate_7d < -3:
        narratives.append(
            f"↘️ Tu fitness está bajando ({ramp_rate_7d:.1f} CTL/semana). Retomar entrenamientos."
        )
    else:
        narratives.append("→ Tu fitness está estable. Buen mantenimiento.")

    # ACWR
    if acwr is not None:
        if acwr > 1.5:
            narratives.append(
                f"🔴 ACWR {acwr} — riesgo alto de lesión. Reducir volumen esta semana."
            )
        elif acwr > 1.3:
            narratives.append(f"🟡 ACWR {acwr} — zona de precaución. No aumentar carga.")
        elif acwr >= 0.8:
            narratives.append(f"🟢 ACWR {acwr} — zona segura. Podés entrenar con normalidad.")
        elif acwr > 0:
            narratives.append(f"🔵 ACWR {acwr} — desentrenamiento. Aumentar gradualmente.")

    # Compliance
    if compliance_pct is not None and compliance_pct > 0:
        if compliance_pct >= 90:
            narratives.append(f"✅ Compliance {compliance_pct}% — excelente adherencia al plan.")
        elif compliance_pct >= 70:
            narratives.append(
                f"📊 Compliance {compliance_pct}% — buena adherencia, hay margen de mejora."
            )
        else:
            narratives.append(
                f"⚠️ Compliance {compliance_pct}% — baja adherencia al plan. Hablar con tu coach."
            )

    # Readiness — may be None when athlete has no data yet (BUG-8 fix)
    if readiness_score is not None:
        if readiness_score <= 25:
            narratives.append("🔴 Readiness bajo — recuperación recomendada antes de sesiones intensas.")
        elif readiness_score <= 50:
            narratives.append("🟡 Readiness moderado — entrenar con precaución.")
        elif readiness_score >= 75:
            narratives.append("🟢 Readiness alto — listo para entrenar fuerte.")

    return narratives


def _build_snapshot(org, athlete_user, alumno, athlete_membership, period_days, coach_message, coach_user):
    """
    Assemble the complete point-in-time snapshot dict for the report.
    """
    today = timezone.now().date()
    start_date = today - timedelta(days=period_days - 1)

    # --- PMC data ---
    qs = DailyLoad.objects.filter(
        organization=org,
        athlete=athlete_user,
        date__gte=start_date,
        date__lte=today,
    )
    pmc_payload = _build_pmc_payload(qs, period_days)
    readiness_score, readiness_label, _readiness_rec = _compute_readiness(
        athlete_user, org, pmc_payload["current"]["tsb"]
    )
    current = pmc_payload["current"]
    ctl = current["ctl"]
    atl = current["atl"]
    tsb = current["tsb"]
    acwr = round(atl / ctl, 2) if ctl > 0 else None

    # --- Volume ---
    volume_by_sport = _build_volume_snapshot(org, athlete_user, alumno, start_date, today)

    # --- Compliance ---
    compliance_pct = _build_compliance_snapshot(org, athlete_user, start_date, today)

    # --- Wellness ---
    wellness_avg = _build_wellness_snapshot(org, athlete_user, start_date, today)

    # --- GAP ---
    gap_avg_formatted = _build_gap_snapshot(org, alumno, start_date, today)

    ramp_rate_7d = current.get("ramp_rate_7d", 0.0)

    # --- Narratives ---
    narratives = _build_narratives(ramp_rate_7d, acwr, compliance_pct, readiness_score)

    return {
        "period_days": period_days,
        "generated_at": timezone.now().isoformat(),
        "athlete_name": athlete_user.get_full_name() or athlete_user.username,
        "coach_name": coach_user.get_full_name() or coach_user.username,
        "coach_message": coach_message,
        "kpis": {
            "ctl": round(ctl, 1),
            "atl": round(atl, 1),
            "tsb": round(tsb, 1),
            "readiness_score": readiness_score,
            "readiness_label": readiness_label,
            "ramp_rate_7d": ramp_rate_7d,
            "ramp_rate_28d": current.get("ramp_rate_28d", 0.0),
            "acwr": acwr,
            "gap_avg_formatted": gap_avg_formatted,
        },
        "pmc_days": pmc_payload["days"],
        "projection": pmc_payload["projection"],
        "volume_by_sport": volume_by_sport,
        "compliance_pct": compliance_pct,
        "wellness_avg": wellness_avg,
        "narratives": narratives,
    }


# ==============================================================================
# Authenticated coach endpoints
# ==============================================================================

class CreateReportView(APIView):
    """
    POST /api/coach/athletes/<membership_id>/report/

    Creates an AthleteReport with a 7-day expiry token.
    Returns the shareable URL and a preview of key KPIs.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, membership_id: int):
        org, athlete_membership, athlete_user = _resolve_athlete_membership(
            request, membership_id
        )
        coach_membership = _get_coach_membership(request)

        period_days = int(request.data.get("period_days", 90))
        if period_days < 7 or period_days > 365:
            return Response({"period_days": "Must be between 7 and 365."}, status=400)
        coach_message = str(request.data.get("coach_message", ""))[:2000]

        # Resolve Alumno for volume queries (legacy path)
        from core.models import Alumno
        alumno = Alumno.objects.filter(usuario=athlete_user).first()

        snapshot = _build_snapshot(
            org=org,
            athlete_user=athlete_user,
            alumno=alumno,
            athlete_membership=athlete_membership,
            period_days=period_days,
            coach_message=coach_message,
            coach_user=request.user,
        )

        token = uuid.uuid4().hex
        expires_at = timezone.now() + timedelta(days=_REPORT_TTL_DAYS)

        report = AthleteReport.objects.create(
            token=token,
            organization=org,
            athlete_user=athlete_user,
            coach_user=request.user,
            membership=athlete_membership,
            period_days=period_days,
            coach_message=coach_message,
            snapshot=snapshot,
            expires_at=expires_at,
        )

        report_url = request.build_absolute_uri(f"/report/{token}/")
        kpis = snapshot["kpis"]

        logger.info(
            "athlete_report.created",
            extra={
                "event_name": "athlete_report.created",
                "organization_id": org.pk,
                "coach_user_id": request.user.pk,
                "athlete_user_id": athlete_user.pk,
                "report_id": report.pk,
                "period_days": period_days,
                "outcome": "success",
            },
        )

        return Response({
            "token": token,
            "url": report_url,
            "expires_at": expires_at.isoformat(),
            "preview": {
                "athlete_name": snapshot["athlete_name"],
                "readiness": kpis["readiness_score"],
                "ctl": kpis["ctl"],
                "acwr": kpis["acwr"],
            },
        }, status=201)


class EmailReportView(APIView):
    """
    POST /api/coach/athletes/<membership_id>/report/<token>/email/

    Sends the report link via email to the specified recipient.
    Validates that the token belongs to the coach's org.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, membership_id: int, token: str):
        org, _, _ = _resolve_athlete_membership(request, membership_id)

        try:
            report = AthleteReport.objects.select_related("athlete_user", "coach_user").get(
                token=token,
                organization=org,
            )
        except AthleteReport.DoesNotExist:
            return Response({"detail": "Report not found."}, status=404)

        if report.is_expired():
            return Response({"detail": "Report has expired."}, status=410)

        recipient_email = str(request.data.get("recipient_email", "")).strip()
        if not recipient_email or "@" not in recipient_email:
            return Response({"recipient_email": "Valid email required."}, status=400)

        athlete_name = report.snapshot.get("athlete_name", "Atleta")
        coach_name = report.snapshot.get("coach_name", "Tu coach")
        report_url = request.build_absolute_uri(f"/report/{token}/")

        subject = f"Tu reporte de entrenamiento — Quantoryn"
        body = (
            f"Hola {athlete_name},\n\n"
            f"Tu coach {coach_name} te envió tu reporte de entrenamiento de los últimos "
            f"{report.period_days} días.\n\n"
            f"Podés verlo online en el siguiente link:\n{report_url}\n\n"
            f"El link expira el {report.expires_at.strftime('%d/%m/%Y')}.\n\n"
            f"— Quantoryn"
        )

        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=None,  # uses DEFAULT_FROM_EMAIL
                recipient_list=[recipient_email],
                fail_silently=False,
            )
        except Exception as exc:
            logger.warning(
                "athlete_report.email_failed",
                extra={
                    "event_name": "athlete_report.email_failed",
                    "organization_id": org.pk,
                    "coach_user_id": request.user.pk,
                    "report_id": report.pk,
                    "outcome": "error",
                },
            )
            return Response({"detail": "Failed to send email."}, status=500)

        logger.info(
            "athlete_report.email_sent",
            extra={
                "event_name": "athlete_report.email_sent",
                "organization_id": org.pk,
                "coach_user_id": request.user.pk,
                "report_id": report.pk,
                "outcome": "success",
            },
        )
        return Response({"sent": True})


# ==============================================================================
# Public endpoints (no authentication required)
# ==============================================================================

def public_report_view(request, token: str):
    """
    GET /report/<token>/

    Public, no-auth page that renders a training report from a stable snapshot.
    Increments view_count on each access; sets viewed_at on first access.
    Returns 404 for invalid or expired tokens.
    """
    try:
        report = AthleteReport.objects.get(token=token)
    except AthleteReport.DoesNotExist:
        return render(request, "report/expired.html", status=404)

    if report.is_expired():
        return render(request, "report/expired.html", status=404)

    # Track views
    report.view_count += 1
    if report.viewed_at is None:
        report.viewed_at = timezone.now()
    report.save(update_fields=["view_count", "viewed_at"])

    snapshot = report.snapshot
    kpis = snapshot.get("kpis", {})

    # Build OG description for WhatsApp preview
    og_description = (
        f"Fitness: {kpis.get('ctl', 0):.0f} CTL | "
        f"Readiness: {kpis.get('readiness_score', 0)}/100 | "
        f"Coach: {snapshot.get('coach_name', '')}"
    )

    from django.conf import settings
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")

    projection = snapshot.get("projection", [])
    projection_2w_ctl = projection[-1]["ctl"] if projection else None

    # Inject derived field into snapshot for template access
    snapshot["projection_2w_ctl"] = projection_2w_ctl

    context = {
        "report": report,
        "snapshot": snapshot,
        "kpis": kpis,
        "og_description": og_description,
        "report_url": request.build_absolute_uri(),
        "volume_items": list(snapshot.get("volume_by_sport", {}).items()),
        "pmc_days_json": snapshot.get("pmc_days", []),
        "frontend_url": frontend_url,
    }
    return render(request, "report/public_report.html", context)
