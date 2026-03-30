"""
Canonical user identity endpoint.

GET /api/me/ - Returns authenticated user's identity with role and context.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import Alumno, Membership


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
