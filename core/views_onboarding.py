"""
PR-149: Athlete registration and onboarding views.

Public endpoints for registration (email + Google OAuth).
Authenticated endpoint for onboarding completion.
"""

import logging
import uuid

from django.conf import settings as django_settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import (
    Athlete,
    AthleteAvailability,
    AthleteGoal,
    AthleteInvitation,
    AthleteProfile,
    AthleteSubscription,
    Membership,
    OrgOAuthCredential,
    RaceEvent,
    TeamInvitation,
)
from core.serializers_onboarding import (
    GoogleAuthSerializer,
    OnboardingCompleteSerializer,
    RegisterSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


def _jwt_pair(user):
    """Return access/refresh JWT pair for a user."""
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


class RegisterView(APIView):
    """
    POST /api/auth/register/
    Public registration with email + password. Returns JWT pair.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        if email and User.objects.filter(email__iexact=email).exists():
            return Response(
                {
                    "detail": "Ya existe una cuenta con este email.",
                    "code": "email_exists",
                    "action": "login",
                    "login_url": "/login",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            _jwt_pair(user),
            status=status.HTTP_201_CREATED,
        )


class GoogleAuthView(APIView):
    """
    POST /api/auth/google/
    Verify Google ID token and return JWT pair.
    Creates user on first login.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        credential = serializer.validated_data["credential"]

        try:
            from google.auth.transport import requests as google_requests
            from google.oauth2 import id_token

            payload = id_token.verify_oauth2_token(
                credential,
                google_requests.Request(),
                django_settings.GOOGLE_CLIENT_ID,
            )
        except ValueError:
            return Response(
                {"detail": "Token de Google inválido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = payload.get("email", "").lower().strip()
        if not email:
            return Response(
                {"detail": "No se pudo obtener el email de Google."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Lookup by email. If multiple users share an email (legacy data),
        # pick the first one deterministically to avoid IntegrityError.
        existing = User.objects.filter(email=email).first()
        if existing:
            user, created = existing, False
        else:
            user = User.objects.create_user(
                username=f"{email.split('@')[0]}_{uuid.uuid4().hex[:6]}",
                email=email,
                first_name=payload.get("given_name", ""),
                last_name=payload.get("family_name", ""),
            )
            created = True

        logger.info(
            "athlete_google_auth",
            extra={
                "user_id": user.id,
                "created": created,
                "method": "google",
            },
        )

        return Response(_jwt_pair(user), status=status.HTTP_200_OK)


def _create_mp_preapproval(invitation, user_email, coach_plan=None):
    """
    Create MercadoPago preapproval for an invitation.

    Returns (mp_data, error_response). On success error_response is None.
    coach_plan can be passed explicitly (athlete-selected) or read from invitation.
    """
    plan = coach_plan or invitation.coach_plan
    if not plan:
        return None, Response(
            {"detail": "No se seleccionó un plan."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        cred = OrgOAuthCredential.objects.get(
            organization=invitation.organization,
            provider="mercadopago",
        )
    except OrgOAuthCredential.DoesNotExist:
        return None, Response(
            {"detail": "El coach no tiene MercadoPago conectado."},
            status=status.HTTP_402_PAYMENT_REQUIRED,
        )

    frontend_url = getattr(
        django_settings, "FRONTEND_URL", "http://localhost:3000"
    )

    if not plan.mp_plan_id:
        # Lazy creation: the coach's plan hasn't been registered in MP yet.
        from integrations.mercadopago.subscriptions import create_preapproval_plan
        try:
            org_name = invitation.organization.name
            mp_plan = create_preapproval_plan(
                access_token=cred.access_token,
                name=f"{org_name} — {plan.name}",
                price_ars=plan.price_ars,
                back_url=f"{frontend_url}/payment/callback",
            )
            plan.mp_plan_id = mp_plan["id"]
            plan.save(update_fields=["mp_plan_id", "updated_at"])
        except Exception as exc:
            logger.error(
                "onboarding.mp_plan_create_error",
                extra={
                    "organization_id": invitation.organization_id,
                    "plan_id": plan.pk,
                    "error_type": type(exc).__name__,
                    "outcome": "error",
                },
            )
            return None, Response(
                {"detail": "Error al configurar el plan en MercadoPago."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    # FIX-1: Create individual preapproval for this athlete so we can stamp its ID
    # to AthleteSubscription BEFORE redirecting to MP checkout.
    # Using plan init_point (generic URL) would not give us a preapproval_id,
    # causing auto-activation to fail when the webhook arrives.
    from integrations.mercadopago.subscriptions import create_coach_athlete_preapproval
    try:
        mp_preapproval = create_coach_athlete_preapproval(
            access_token=cred.access_token,
            mp_plan_id=plan.mp_plan_id,
            payer_email=user_email,
            reason=f"Quantoryn {plan.name} — {invitation.organization.name}",
            back_url=f"{frontend_url}/payment/callback",
        )
    except Exception as exc:
        logger.error(
            "onboarding.mp_preapproval_create_error",
            extra={
                "organization_id": invitation.organization_id,
                "plan_id": plan.pk,
                "error_type": type(exc).__name__,
                "outcome": "error",
            },
        )
        return None, Response(
            {"detail": "Error al crear el preapproval en MercadoPago."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    preapproval_id = mp_preapproval.get("id")
    init_point = mp_preapproval.get("init_point")

    if not init_point:
        logger.error(
            "onboarding.mp_init_point_missing",
            extra={
                "organization_id": invitation.organization_id,
                "mp_plan_id": plan.mp_plan_id,
                "outcome": "error",
            },
        )
        return None, Response(
            {"detail": "MercadoPago no retornó un link de pago."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return {"id": preapproval_id, "init_point": init_point}, None


class OnboardingCompleteView(APIView):
    """
    POST /api/onboarding/complete/
    Atomically creates Athlete + Profile + Availability + accepts invitation.
    Then creates MP preapproval (outside transaction — external call).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = OnboardingCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        invitation = serializer.context.get("invitation")
        org = invitation.organization if invitation else serializer.context.get("join_organization")
        user = request.user

        # Resolve plan: from invitation (pre-assigned) or athlete selection
        coach_plan = (
            (invitation.coach_plan if invitation else None)
            or serializer.context.get("selected_plan")
        )

        # Check idempotency (Law 5) — any role counts as "already member"
        already_member = Membership.objects.filter(
            user=user, organization=org,
        ).exists()
        if already_member:
            return Response(
                {"redirect_url": "/dashboard", "already_member": True},
            )

        try:
            with transaction.atomic():
                # Update user profile
                user.first_name = data["first_name"]
                user.last_name = data["last_name"]
                user.save(update_fields=["first_name", "last_name"])

                # Create Membership (get_or_create for resilience)
                Membership.objects.get_or_create(
                    user=user,
                    organization=org,
                    defaults={"role": "athlete"},
                )

                # Create Athlete (get_or_create for resilience)
                athlete, _ = Athlete.objects.get_or_create(
                    user=user,
                    organization=org,
                    defaults={
                        "phone_number": data["phone_number"],
                        "location_city": data.get("city", ""),
                    },
                )

                # Auto-link to org's primary coach (safe for single-coach orgs)
                if not athlete.coach:
                    from core.models import Coach as _Coach
                    org_coach = _Coach.objects.filter(
                        organization=org, is_active=True
                    ).first()
                    if org_coach:
                        athlete.coach = org_coach
                        athlete.save(update_fields=["coach"])

                # Calculate age from birth_date
                today = timezone.now().date()
                bd = data["birth_date"]
                age = (
                    today.year - bd.year
                    - ((today.month, today.day) < (bd.month, bd.day))
                )

                # Create AthleteProfile (skip if already exists)
                if not AthleteProfile.objects.filter(athlete=athlete).exists():
                    AthleteProfile.objects.create(
                        athlete=athlete,
                        organization=org,
                        birth_date=data["birth_date"],
                        age=age,
                        height_cm=data["height_cm"],
                        weight_kg=data["weight_kg"],
                        blood_type=data.get("blood_type", ""),
                        clothing_size=data.get("clothing_size", ""),
                        instagram_handle=data.get("instagram_handle", ""),
                        profession=data.get("profession", ""),
                        emergency_contact_name=data.get("emergency_contact_name", ""),
                        emergency_contact_phone=data.get("emergency_contact_phone", ""),
                        training_age_years=data.get("training_age_years"),
                        pace_1000m_seconds=data.get("pace_1000m_seconds"),
                        max_hr_bpm=data.get("max_hr_bpm"),
                        resting_hr_bpm=data.get("resting_hr_bpm"),
                        vo2max=data.get("vo2max"),
                        weekly_available_hours=data.get("weekly_available_hours"),
                        preferred_training_time=data.get("preferred_training_time", ""),
                        best_10k_minutes=data.get("best_10k_minutes"),
                        best_21k_minutes=data.get("best_21k_minutes"),
                        best_42k_minutes=data.get("best_42k_minutes"),
                        menstrual_tracking_enabled=data.get(
                            "menstrual_tracking_enabled", False,
                        ),
                        menstrual_cycle_days=data.get("menstrual_cycle_days"),
                        dominant_discipline="trail",
                        updated_by=user,
                    )

                # Create availability (7 entries, skip if already exist)
                if not AthleteAvailability.objects.filter(athlete=athlete).exists():
                    availability_objs = [
                        AthleteAvailability(
                            athlete=athlete,
                            organization=org,
                            day_of_week=entry["day_of_week"],
                            is_available=entry["is_available"],
                            reason=entry.get("reason", ""),
                            preferred_time=entry.get("preferred_time", ""),
                        )
                        for entry in data["availability"]
                    ]
                    AthleteAvailability.objects.bulk_create(availability_objs)

                # Create goals — supports both single `goal` and array `goals`
                all_goals = data.get("goals", [])
                single_goal = data.get("goal")
                if single_goal and not all_goals:
                    all_goals = [single_goal]

                for goal_data in all_goals:
                    race_event, _ = RaceEvent.objects.get_or_create(
                        organization=org,
                        name=goal_data["race_name"],
                        event_date=goal_data["race_date"],
                        defaults={
                            "discipline": "trail",
                            "distance_km": goal_data.get("distance_km"),
                            "elevation_gain_m": goal_data.get("elevation_gain_m"),
                            "created_by": user,
                        },
                    )
                    AthleteGoal.objects.get_or_create(
                        organization=org,
                        athlete=athlete,
                        priority=goal_data.get("priority", "A"),
                        status="active",
                        defaults={
                            "target_event": race_event,
                            "title": goal_data["race_name"],
                            "target_date": goal_data["race_date"],
                            "created_by": user,
                        },
                    )

                # Mark invitation accepted (or create one for join-link tracking)
                if invitation:
                    invitation.status = AthleteInvitation.Status.ACCEPTED
                    invitation.accepted_at = timezone.now()
                    invitation.save(update_fields=["status", "accepted_at"])
                else:
                    invitation = AthleteInvitation.objects.create(
                        organization=org,
                        coach_plan=coach_plan,
                        email=user.email or "",
                        status=AthleteInvitation.Status.ACCEPTED,
                        accepted_at=timezone.now(),
                        expires_at=timezone.now(),
                    )

        except Exception as exc:
            logger.error(
                "onboarding.transaction_error",
                extra={
                    "user_id": user.pk,
                    "error_type": type(exc).__name__,
                    "outcome": "error",
                },
            )
            return Response(
                {"detail": f"Error al completar el registro: {type(exc).__name__}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Outside transaction: MP preapproval (external HTTP)
        mp_data, error_response = _create_mp_preapproval(
            invitation, user.email or invitation.email, coach_plan=coach_plan,
        )
        if error_response:
            # Athlete + profile created, but payment setup failed.
            # They can retry payment later. Log and return dashboard redirect.
            logger.warning(
                "onboarding.mp_preapproval_deferred",
                extra={
                    "organization_id": org.pk,
                    "athlete_id": athlete.pk,
                    "user_id": user.pk,
                    "outcome": "deferred",
                },
            )
            # PR-152: Create subscription with 7-day trial (even if MP fails)
            from datetime import timedelta
            trial_end = timezone.now() + timedelta(days=7)

            AthleteSubscription.objects.get_or_create(
                athlete=athlete,
                coach_plan=coach_plan,
                defaults={
                    "organization": org,
                    "status": AthleteSubscription.Status.PENDING,
                    "trial_ends_at": trial_end,
                },
            )

            # PR-152: Notify coach about new athlete registration
            try:
                from core.models import Coach, InternalMessage
                coach_record = Coach.objects.filter(
                    organization=org,
                ).select_related("user").first()
                coach_user = coach_record.user if (coach_record and coach_record.user) else None
                if not coach_user:
                    # Fallback: find coach/owner via Membership
                    coach_membership = Membership.objects.filter(
                        organization=org,
                        role__in=["owner", "coach"],
                        is_active=True,
                    ).select_related("user").first()
                    coach_user = coach_membership.user if coach_membership else None
                if coach_user:
                    athlete_name = f"{user.first_name} {user.last_name}".strip() or user.username
                    plan_name = coach_plan.name if coach_plan else "Sin plan"
                    InternalMessage.objects.create(
                        organization=org,
                        sender=user,
                        recipient=coach_user,
                        content=f"🆕 {athlete_name} se unió a tu equipo (Plan {plan_name})",
                        alert_type="athlete_registered",
                    )
                    # Welcome message TO the athlete
                    InternalMessage.objects.create(
                        organization=org,
                        sender=coach_user,
                        recipient=user,
                        content=f"🎉 ¡Bienvenido a {org.name}! Tu coach ya puede verte y asignarte entrenamientos.",
                        alert_type="athlete_welcome",
                    )
            except Exception:
                pass  # Best-effort notification

            return Response({
                "redirect_url": "/dashboard",
                "payment_pending": True,
            })

        preapproval_id = mp_data.get("id")
        init_point = mp_data.get("init_point")

        # Create AthleteSubscription with trial
        from datetime import timedelta
        trial_end = timezone.now() + timedelta(days=7)

        invitation.mp_preapproval_id = preapproval_id
        invitation.save(update_fields=["mp_preapproval_id"])

        sub, created = AthleteSubscription.objects.get_or_create(
            athlete=athlete,
            coach_plan=coach_plan,
            defaults={
                "organization": org,
                "status": AthleteSubscription.Status.PENDING,
                "mp_preapproval_id": preapproval_id,
                "trial_ends_at": trial_end,
            },
        )
        # Stamp preapproval_id if record already existed without it (e.g. MP failed on first attempt)
        if not created and preapproval_id and not sub.mp_preapproval_id:
            sub.mp_preapproval_id = preapproval_id
            sub.save(update_fields=["mp_preapproval_id", "updated_at"])

        # PR-152: Notify coach about new athlete registration
        try:
            from core.models import Coach, InternalMessage
            coach_record = Coach.objects.filter(
                organization=org,
            ).select_related("user").first()
            coach_user = coach_record.user if (coach_record and coach_record.user) else None
            if not coach_user:
                # Fallback: find coach/owner via Membership
                coach_membership = Membership.objects.filter(
                    organization=org,
                    role__in=["owner", "coach"],
                    is_active=True,
                ).select_related("user").first()
                coach_user = coach_membership.user if coach_membership else None
            if coach_user:
                athlete_name = f"{user.first_name} {user.last_name}".strip() or user.username
                plan_name = coach_plan.name if coach_plan else "Sin plan"
                InternalMessage.objects.create(
                    organization=org,
                    sender=user,
                    recipient=coach_user,
                    content=f"🆕 {athlete_name} se unió a tu equipo (Plan {plan_name})",
                    alert_type="athlete_registered",
                )
                # Welcome message TO the athlete
                InternalMessage.objects.create(
                    organization=org,
                    sender=coach_user,
                    recipient=user,
                    content=f"🎉 ¡Bienvenido a {org.name}! Tu coach ya puede verte y asignarte entrenamientos.",
                    alert_type="athlete_welcome",
                )
        except Exception:
            pass  # Best-effort notification

        logger.info(
            "onboarding_complete",
            extra={
                "organization_id": org.pk,
                "athlete_id": athlete.pk,
                "user_id": user.pk,
                "plan": coach_plan.name if coach_plan else "none",
                "outcome": "success",
            },
        )

        return Response(
            {"redirect_url": init_point},
            status=status.HTTP_201_CREATED,
        )


# ==============================================================================
# PR-165a: TeamJoinView — public endpoint to preview and accept a team invite
# ==============================================================================

class TeamJoinView(APIView):
    """
    GET  /api/team-join/{token}/  — public; returns invitation info (org, role, status).
    POST /api/team-join/{token}/  — accepts first_name, last_name, email, password.
                                    Creates User + Membership. Returns JWT pair.
                                    If user is already authenticated (JWT header present),
                                    only creates the Membership — no registration needed.

    Note: authentication_classes uses DEFAULT (JWT) so an authenticated user's token
    is recognised. permission_classes = AllowAny so unauthenticated requests still work.
    """

    permission_classes = [AllowAny]
    # Do NOT set authentication_classes = [] here — we need JWT auth to resolve
    # request.user for the "already logged in" path.

    def _get_invitation(self, token):
        try:
            return TeamInvitation.objects.select_related("organization").get(token=token)
        except TeamInvitation.DoesNotExist:
            return None

    def _validate_invitation(self, invitation, email=None):
        """Return (None, error_response) or (invitation, None)."""
        if invitation is None:
            return None, Response(
                {"detail": "Invitación no encontrada.", "code": "not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        if invitation.status == TeamInvitation.Status.ACCEPTED:
            return None, Response(
                {"detail": "Esta invitación ya fue usada.", "code": "already_used"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if invitation.is_expired or invitation.status == TeamInvitation.Status.EXPIRED:
            return None, Response(
                {"detail": "Esta invitación ha expirado.", "code": "expired"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if email and invitation.email and invitation.email.lower() != email.lower():
            return None, Response(
                {"detail": "Este enlace no está destinado a tu email.", "code": "email_mismatch"},
                status=status.HTTP_403_FORBIDDEN,
            )
        return invitation, None

    def get(self, request, token):
        invitation = self._get_invitation(token)
        inv, err = self._validate_invitation(invitation)
        if err:
            return err
        return Response({
            "org_name": inv.organization.name,
            "role": inv.role,
            "status": inv.status,
            "expires_at": inv.expires_at,
        })

    def post(self, request, token):
        invitation = self._get_invitation(token)
        # Only validate email match when the user is NOT authenticated
        # (authenticated users are identified by their session/token, not by email in body)
        email = "" if (request.user and request.user.is_authenticated) else request.data.get("email", "").lower().strip()
        inv, err = self._validate_invitation(invitation, email=email)
        if err:
            return err

        with transaction.atomic():
            # Authenticated user path: just create membership
            if request.user and request.user.is_authenticated:
                user = request.user
            else:
                # Registration path
                first_name = request.data.get("first_name", "").strip()
                last_name  = request.data.get("last_name", "").strip()
                password   = request.data.get("password", "")

                if not email or not password:
                    return Response(
                        {"detail": "email y password son requeridos."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                existing = User.objects.filter(email=email).first()
                if existing:
                    # User exists — verify password and log them in
                    if not existing.check_password(password):
                        return Response(
                            {"detail": "Credenciales incorrectas."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                    user = existing
                else:
                    user = User.objects.create_user(
                        username=email,
                        email=email,
                        first_name=first_name,
                        last_name=last_name,
                        password=password,
                    )

            # Create Membership (idempotent — skip if already exists)
            membership, created = Membership.objects.get_or_create(
                user=user,
                organization=inv.organization,
                defaults={"role": inv.role},
            )
            if not created and membership.role != inv.role:
                # Update role to invited role if membership already existed with different role
                membership.role = inv.role
                membership.save(update_fields=["role"])

            # Auto-create Coach record when role is 'coach' (PR-165c)
            if inv.role == "coach":
                from core.models import Coach
                Coach.objects.get_or_create(
                    user=user,
                    organization=inv.organization,
                    defaults={"is_active": True},
                )

            # Mark invitation as accepted
            inv.status = TeamInvitation.Status.ACCEPTED
            inv.accepted_by = user
            inv.accepted_at = timezone.now()
            inv.save(update_fields=["status", "accepted_by", "accepted_at"])

        logger.info(
            "team_invitation_accepted",
            extra={
                "organization_id": inv.organization.id,
                "user_id": user.id,
                "role": inv.role,
                "invitation_token": str(inv.token),
            },
        )

        # Send welcome email (fire-and-forget; errors are logged, not raised)
        if user.email:
            try:
                from core.auth_views import _send_welcome_email
                _send_welcome_email(
                    to_email=user.email,
                    first_name=user.first_name or user.email.split("@")[0],
                    org_name=inv.organization.name,
                    role=inv.role,
                )
            except Exception as _exc:
                logger.error(
                    "welcome_email.dispatch_failed",
                    extra={"user_id": user.id, "exc": str(_exc), "outcome": "error"},
                )

        return Response(_jwt_pair(user), status=status.HTTP_200_OK)
