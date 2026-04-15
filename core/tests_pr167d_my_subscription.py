"""
PR-167d — MySubscriptionView org_id validation tests.

Tests:
1. GET ?org_id=undefined returns 400 (not 500 ValueError)
2. GET ?org_id=abc (non-integer) returns 400
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()

MY_SUB_URL = "/api/me/subscription/"


@pytest.fixture
def auth_user():
    user = User.objects.create_user(username="user_mysub", email="mysub@test.com", password="pw")
    return user


@pytest.mark.django_db
def test_my_subscription_org_id_undefined_returns_400(auth_user):
    """
    GET /api/me/subscription/?org_id=undefined must return 400, not 500.
    This was the production Sentry crash: int("undefined") raises ValueError.
    """
    client = APIClient()
    client.force_authenticate(user=auth_user)

    res = client.get(MY_SUB_URL, {"org_id": "undefined"})

    assert res.status_code == 400
    assert "org_id" in res.json().get("detail", "").lower() or \
           "inválido" in res.json().get("detail", "")


@pytest.mark.django_db
def test_my_subscription_org_id_non_integer_returns_400(auth_user):
    """
    GET /api/me/subscription/?org_id=abc must return 400.
    """
    client = APIClient()
    client.force_authenticate(user=auth_user)

    res = client.get(MY_SUB_URL, {"org_id": "abc"})

    assert res.status_code == 400
