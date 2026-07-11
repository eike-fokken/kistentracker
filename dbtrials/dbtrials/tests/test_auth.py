"""Tests for the authentication flows (cookie/browser and bearer/server)."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from dbtrials.models import Cookinggroup, Packstreet

User = get_user_model()

USERNAME = "smoke"
PASSWORD = "smoke-pass-123"


class CookieAuthTests(TestCase):
    """The browser cookie login flow and its CSRF protection."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username=USERNAME, password=PASSWORD, role="admin"
        )
        # enforce_csrf_checks mirrors a real browser: CSRF is verified.
        self.client = Client(enforce_csrf_checks=True)

    def _csrf_token(self) -> str:
        response = self.client.get("/api/auth/csrf")
        self.assertEqual(response.status_code, 200)
        return self.client.cookies["csrftoken"].value

    def test_csrf_bootstrap_sets_readable_cookie(self) -> None:
        self._csrf_token()
        self.assertIn("csrftoken", self.client.cookies)
        # Must stay readable by JS so the SPA can echo it as X-CSRFToken.
        self.assertFalse(self.client.cookies["csrftoken"]["httponly"])

    def test_login_without_csrf_is_rejected(self) -> None:
        self._csrf_token()
        response = self.client.post(
            "/api/auth/login",
            data={"username": USERNAME, "password": PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_login_sets_session_cookie_and_returns_user(self) -> None:
        token = self._csrf_token()
        response = self.client.post(
            "/api/auth/login",
            data={"username": USERNAME, "password": PASSWORD},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"username": USERNAME, "is_admin": True, "show_consumables": True},
        )
        self.assertIn("sessionid", response.cookies)
        self.assertTrue(response.cookies["sessionid"]["httponly"])

    def test_login_with_bad_password_is_unauthorized(self) -> None:
        token = self._csrf_token()
        response = self.client.post(
            "/api/auth/login",
            data={"username": USERNAME, "password": "wrong"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 401)

    def test_me_via_cookie(self) -> None:
        token = self._csrf_token()
        self.client.post(
            "/api/auth/login",
            data={"username": USERNAME, "password": PASSWORD},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        response = self.client.get("/api/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"username": USERNAME, "is_admin": True, "show_consumables": True},
        )

    def test_unsafe_request_requires_csrf(self) -> None:
        token = self._csrf_token()
        self.client.post(
            "/api/auth/login",
            data={"username": USERNAME, "password": PASSWORD},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        # POST without the X-CSRFToken header is rejected even when authed.
        response = self.client.post(
            "/api/groups", data={"name": "G1"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 403)

    def test_create_group_with_cookie_and_csrf(self) -> None:
        packstreet = Packstreet.objects.create(name="Main")
        token = self._csrf_token()
        self.client.post(
            "/api/auth/login",
            data={"username": USERNAME, "password": PASSWORD},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        token = self.client.cookies["csrftoken"].value
        response = self.client.post(
            "/api/groups",
            data={"name": "G1", "internal_id": "1", "packstreet_id": packstreet.pk},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Cookinggroup.objects.filter(name="G1").exists())

    def test_logout_clears_cookies(self) -> None:
        token = self._csrf_token()
        self.client.post(
            "/api/auth/login",
            data={"username": USERNAME, "password": PASSWORD},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        token = self.client.cookies["csrftoken"].value
        response = self.client.post("/api/auth/logout", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        # Session cookie is expired (empty value) after logout.
        self.assertEqual(response.cookies["sessionid"].value, "")


class BearerAuthTests(TestCase):
    """The server-to-server bearer token flow stays available."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username=USERNAME, password=PASSWORD, role="admin"
        )

    def test_token_pair_and_bearer_access(self) -> None:
        response = self.client.post(
            "/api/token/pair",
            data={"username": USERNAME, "password": PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        access = response.json()["access"]

        # Bearer requests need no CSRF token.
        response = self.client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"username": USERNAME, "is_admin": True, "show_consumables": True},
        )

    def test_anonymous_request_is_unauthorized(self) -> None:
        response = self.client.get("/api/me")
        self.assertEqual(response.status_code, 401)
