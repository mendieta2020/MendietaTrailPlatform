import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import CoachProfile, get_onboarding_completed


@pytest.mark.django_db
def test_new_user_onboarding_default_false():
    user = User.objects.create_user(username="coach1", password="pass12345")

    assert get_onboarding_completed(user) is False
    assert CoachProfile.objects.filter(user=user).count() == 0


@pytest.mark.django_db
def test_onboarding_complete_endpoint_sets_flag():
    user = User.objects.create_user(username="coach2", password="pass12345")
    client = APIClient()
    client.force_authenticate(user=user)

    response = client.post("/api/onboarding/complete/")

    assert response.status_code == 200
    assert response.data == {"ok": True, "onboarding_completed": True}

    profile = CoachProfile.objects.get(user=user)
    assert profile.onboarding_completed is True


@pytest.mark.django_db
def test_onboarding_complete_requires_auth():
    client = APIClient()

    response = client.post("/api/onboarding/complete/")

    assert response.status_code in {401, 403}
