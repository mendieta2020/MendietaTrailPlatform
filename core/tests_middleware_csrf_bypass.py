from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from core.middleware import BearerAuthCsrfBypassMiddleware


def _middleware_call(request):
    middleware = BearerAuthCsrfBypassMiddleware(lambda _request: HttpResponse("ok"))
    return middleware(request)


def test_bearer_without_cookies_sets_bypass():
    request = RequestFactory().post(
        "/", HTTP_AUTHORIZATION="Bearer test-token"
    )

    _middleware_call(request)

    assert request._dont_enforce_csrf_checks is True


def test_bearer_with_session_cookie_does_not_bypass():
    request = RequestFactory().post(
        "/", HTTP_AUTHORIZATION="Bearer test-token"
    )
    request.COOKIES["sessionid"] = "abc"

    _middleware_call(request)

    assert request._dont_enforce_csrf_checks is False


@override_settings(
    USE_COOKIE_AUTH=True,
    COOKIE_AUTH_ACCESS_NAME="mt_access",
    COOKIE_AUTH_REFRESH_NAME="mt_refresh",
)
def test_bearer_with_cookie_auth_access_does_not_bypass():
    request = RequestFactory().post(
        "/", HTTP_AUTHORIZATION="Bearer test-token"
    )
    request.COOKIES["mt_access"] = "token"

    _middleware_call(request)

    assert request._dont_enforce_csrf_checks is False


def test_no_bearer_header_does_not_set_bypass_attribute():
    request = RequestFactory().post("/")

    _middleware_call(request)

    assert not getattr(request, "_dont_enforce_csrf_checks", False)
