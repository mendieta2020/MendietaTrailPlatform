"""
Canonical user identity endpoint.

GET /api/me/ - Returns authenticated user's identity with role and context.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import Alumno, Membership


def compute_subscription_status(user, org_id):
    """
    Returns the athlete's effective subscription status for visibility gates.

    Values:
        "active"        — paid subscription, full access
        "trial"         — trial period still valid, full access
        "paused"        — paused, limited access
        "cancelled"     — cancelled, hard paywall
        "trial_expired" — trial ended and not active, hard paywall
        "none"          — no subscription record found, hard paywall

    PR-168a: Single source of truth for frontend visibility decisions.
    """
    from django.utils import timezone as tz
    from .models import AthleteSubscription

    sub = AthleteSubscription.objects.filter(
        athlete__user=user,
        organization_id=org_id,
    ).first()

    if sub is None:
        return "none"

    if sub.status == "active":
        return "active"
    if sub.status == "paused":
        return "paused"
    if sub.status == "cancelled":
        return "cancelled"

    # pending / overdue / suspended — check trial
    if sub.trial_ends_at and sub.trial_ends_at > tz.now():
        return "trial"

    return "trial_expired"


class UserIdentityView(APIView):
    """
    GET /api/me/

    Returns canonical authenticated user identity.

    Role resolution order (P1 architecture takes precedence):
    1. If user has an active P1 Membership, use membership.role.
       Non-athlete roles (owner, coach, admin, staff) are returned immediately.
       Athlete role falls through to also populate legacy athlete_id/coach_id.
    2. If no Membership, fall back to legacy Alumno lookup.
    3. If neither, default to "coach".

    Response schema:
    {
        "id": int,
        "username": str,
        "email": str,
        "role": "owner" | "coach" | "admin" | "staff" | "athlete",
        "coach_id": int (optional, if role=athlete),
        "athlete_id": int (optional, if role=athlete)
    }

    Multi-tenant safe: Returns only current user's data.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Return canonical user identity"""
        user = request.user

        # Base identity (always present)
        identity = {
            "id": user.id,
            "username": user.username,
            "email": user.email or "",
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
        }

        # --- P1 Membership check (takes precedence over legacy Alumno) ---
        try:
            membership = Membership.objects.select_related(
                "organization",
            ).get(user=user, is_active=True)
            p1_role = membership.role  # 'owner' | 'coach' | 'athlete' | 'staff'
            identity["role"] = p1_role

            # PR-151: Include org context so all pages can resolve organization
            identity["org_id"] = membership.organization_id
            identity["org_name"] = membership.organization.name

            # For non-athlete P1 roles we are done — no Alumno lookup needed.
            if p1_role != Membership.Role.ATHLETE:
                return Response(identity, status=status.HTTP_200_OK)

            # Athlete: also populate legacy IDs for backward compatibility.
            try:
                alumno = Alumno.objects.select_related('entrenador').get(usuario=user)
                identity["athlete_id"] = alumno.id
                if alumno.entrenador:
                    identity["coach_id"] = alumno.entrenador.id
            except Alumno.DoesNotExist:
                pass

            # PR-168a: include subscription_status for frontend visibility gates
            identity["subscription_status"] = compute_subscription_status(
                user, membership.organization_id
            )

            return Response(identity, status=status.HTTP_200_OK)

        except Membership.DoesNotExist:
            pass

        # --- Legacy fallback: no P1 Membership found ---
        try:
            alumno = Alumno.objects.select_related('entrenador').get(usuario=user)
            identity["role"] = "athlete"
            identity["athlete_id"] = alumno.id
            if alumno.entrenador:
                identity["coach_id"] = alumno.entrenador.id
        except Alumno.DoesNotExist:
            identity["role"] = "coach"

        return Response(identity, status=status.HTTP_200_OK)
