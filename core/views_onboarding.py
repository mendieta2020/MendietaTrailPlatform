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
    from integrations.mercadopago.subscriptions import (
        create_coach_athlete_preapproval,
    )

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

    if not plan.mp_plan_id:
        return None, Response(
            {"detail": "El plan del coach no está configurado en MercadoPago."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    frontend_url = getattr(
        django_settings, "FRONTEND_URL", "http://localhost:3000"
    )

    try:
        mp_data = create_coach_athlete_preapproval(
            access_token=cred.access_token,
            mp_plan_id=plan.mp_plan_id,
            payer_email=user_email,
            reason=(
                f"Quantoryn {plan.name} "
                f"— {invitation.organization.name}"
            ),
            back_url=f"{frontend_url}/invite/{invitation.token}/callback",
        )
    except Exception as exc:
        logger.error(
            "onboarding.mp_preapproval_error",
            extra={
                "organization_id": invitation.organization_id,
                "invitation_id": invitation.pk,
                "error_type": type(exc).__name__,
                "outcome": "error",
            },
        )
        return None, Response(
            {"detail": "Error al crear la suscripción en MercadoPago."},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return mp_data, None


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
        invitation = serializer.context["invitation"]
        org = invitation.organization
        user = request.user

        # Resolve plan: from invitation (pre-assigned) or athlete selection
        coach_plan = invitation.coach_plan or serializer.context.get("selected_plan")

        # Check idempotency (Law 5)
        already_member = Membership.objects.filter(
            user=user, organization=org, role="athlete",
        ).exists()
        if already_member:
            return Response(
                {"redirect_url": "/dashboard", "already_member": True},
            )

        with transaction.atomic():
            # Update user profile
            user.first_name = data["first_name"]
            user.last_name = data["last_name"]
            user.save(update_fields=["first_name", "last_name"])

            # Create Membership
            Membership.objects.create(
                user=user,
                organization=org,
                role="athlete",
            )

            # Create Athlete
            athlete = Athlete.objects.create(
                user=user,
                organization=org,
                phone_number=data["phone_number"],
                location_city=data.get("city", ""),
            )

            # Calculate age from birth_date
            today = timezone.now().date()
            bd = data["birth_date"]
            age = (
                today.year - bd.year
                - ((today.month, today.day) < (bd.month, bd.day))
            )

            # Create AthleteProfile
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

            # Create availability (7 entries)
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

            # Create goal if provided
            goal_data = data.get("goal")
            if goal_data:
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
                AthleteGoal.objects.create(
                    organization=org,
                    athlete=athlete,
                    target_event=race_event,
                    title=goal_data["race_name"],
                    priority=goal_data.get("priority", "A"),
                    status="active",
                    target_date=goal_data["race_date"],
                    created_by=user,
                )

            # Mark invitation accepted
            invitation.status = AthleteInvitation.Status.ACCEPTED
            invitation.accepted_at = timezone.now()
            invitation.save(update_fields=["status", "accepted_at"])

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
            return Response({
                "redirect_url": "/dashboard",
                "payment_pending": True,
            })

        preapproval_id = mp_data.get("id")
        init_point = mp_data.get("init_point")

        # Create AthleteSubscription
        invitation.mp_preapproval_id = preapproval_id
        invitation.save(update_fields=["mp_preapproval_id"])

        AthleteSubscription.objects.create(
            athlete=athlete,
            organization=org,
            coach_plan=coach_plan,
            status=AthleteSubscription.Status.PENDING,
            mp_preapproval_id=preapproval_id,
        )

        logger.info(
            "onboarding_complete",
            extra={
                "organization_id": org.pk,
                "athlete_id": athlete.pk,
                "user_id": user.pk,
                "plan": invitation.coach_plan.name,
                "outcome": "success",
            },
        )

        return Response(
            {"redirect_url": init_point},
            status=status.HTTP_201_CREATED,
        )
