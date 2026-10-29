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
            {
                "username": USERNAME,
                "is_admin": True,
                "show_consumables": True,
                "prefer_rent": True,
                "barcode_view": True,
                "selected_packstreet_id": None,
            },
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
            {
                "username": USERNAME,
                "is_admin": True,
                "show_consumables": True,
                "prefer_rent": True,
                "barcode_view": True,
                "selected_packstreet_id": None,
            },
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
            {
                "username": USERNAME,
                "is_admin": True,
                "show_consumables": True,
                "prefer_rent": True,
                "barcode_view": True,
                "selected_packstreet_id": None,
            },
        )

    def test_anonymous_request_is_unauthorized(self) -> None:
        response = self.client.get("/api/me")
        self.assertEqual(response.status_code, 401)


class CallerIdentityTests(TestCase):
    """Endpoints resolve the caller from ``request.user``, whatever the transport.

    Both transports set ``request.user``, and ``JWTAuth`` does so
    unconditionally -- even overwriting a user an earlier middleware installed.
    So the attribute endpoints read and the credential that settles the request
    can never disagree.
    """

    def setUp(self) -> None:
        self.session_user = User.objects.create_user(
            username="session-user", password=PASSWORD, role="admin"
        )
        self.token_user = User.objects.create_user(
            username="token-user", password=PASSWORD, role="admin"
        )
        self.packstreet = Packstreet.objects.create(name="Identity Street")
        self.group = Cookinggroup.objects.create(
            name="Identity Group",
            internal_id="ID-1",
            packstreet=self.packstreet,
        )
        self.client = Client(enforce_csrf_checks=True)

    def _login_session(self) -> None:
        """Log the session user in via the cookie flow."""
        self.client.get("/api/auth/csrf")
        token = self.client.cookies["csrftoken"].value
        response = self.client.post(
            "/api/auth/login",
            data={"username": "session-user", "password": PASSWORD},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)

    def _token_user_token(self) -> str:
        response = self.client.post(
            "/api/token/pair",
            data={"username": "token-user", "password": PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access"]

    def test_bearer_token_overrides_a_concurrent_session(self) -> None:
        """JWT is tried first, so a bearer request must identify the token user.

        The session cookie for a *different* account is still valid and is sent
        along; the endpoint must not report the session user.
        """
        self._login_session()
        token = self._token_user_token()

        response = self.client.get("/api/me", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "token-user")

    def test_recorded_action_actor_is_the_token_user(self) -> None:
        """The audit log must record the caller the request authenticated as."""
        self._login_session()
        token = self._token_user_token()

        response = self.client.post(
            f"/api/groups/{self.group.pk}/change-quantity",
            data={"item_type": "kiste", "quantity": 2, "action": "rent"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 200, response.content)

        action = self.group.actions.get()
        self.assertEqual(action.user_id, self.token_user.pk)
        self.assertNotEqual(action.user_id, self.session_user.pk)

    def test_recent_rents_follow_the_requesting_identity(self) -> None:
        """The per-user "kürzlich ausgegeben" figure follows the same identity.

        ``/groups`` reads ``request.user`` while the action endpoints read the
        same attribute; with a token that overrides a concurrent session both
        must land on the token user, or the figure would be attributed to the
        wrong account.
        """
        self._login_session()
        token = self._token_user_token()

        rent = self.client.post(
            f"/api/groups/{self.group.pk}/change-quantity",
            data={"item_type": "kiste", "quantity": 7, "action": "rent"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(rent.status_code, 200, rent.content)

        def recent_rents(authorization: str | None = None) -> int:
            if authorization:
                response = self.client.get(
                    "/api/groups", HTTP_AUTHORIZATION=authorization
                )
            else:
                response = self.client.get("/api/groups")
            self.assertEqual(response.status_code, 200)
            rows = [g for g in response.json() if g["id"] == self.group.pk]
            self.assertEqual(len(rows), 1)
            return rows[0]["recent_rents"]

        # The token user sees their own recent rents.
        self.assertEqual(recent_rents(f"Bearer {token}"), 7)
        # With no bearer header the session user is the caller, and the rent
        # they never made is not credited to them.
        self.assertEqual(recent_rents(), 0)

    def test_permission_policy_sees_the_token_user(self) -> None:
        """Authorization runs on the same principal as the endpoint body.

        A normal session user presenting an admin bearer token must be treated
        as the admin: the token is the credential that settled the request.
        """
        normal = User.objects.create_user(
            username="normal-session", password=PASSWORD, role="user"
        )
        self.client.get("/api/auth/csrf")
        csrf = self.client.cookies["csrftoken"].value
        self.client.post(
            "/api/auth/login",
            data={"username": "normal-session", "password": PASSWORD},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(normal.role, "user")

        admin_token = self._token_user_token()
        response = self.client.post(
            "/api/packstreets",
            data={"name": "Made By Token"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {admin_token}",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Packstreet.objects.filter(name="Made By Token").exists())


class UserPreferencesTests(TestCase):
    """PATCH /me endpoint for show_consumables and selected_packstreet_id."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username=USERNAME, password=PASSWORD, role="admin"
        )
        self.packstreet_a = Packstreet.objects.create(name="Street A")
        self.packstreet_b = Packstreet.objects.create(name="Street B")
        self.client = Client(enforce_csrf_checks=True)

    def _login_and_csrf(self) -> str:
        """Login via cookie and return a fresh CSRF token."""
        self.client.get("/api/auth/csrf")
        token = self.client.cookies["csrftoken"].value
        self.client.post(
            "/api/auth/login",
            data={"username": USERNAME, "password": PASSWORD},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        return self.client.cookies["csrftoken"].value

    def test_patch_me_sets_selected_packstreet(self) -> None:
        token = self._login_and_csrf()
        response = self.client.patch(
            "/api/me",
            data={"selected_packstreet_id": self.packstreet_a.pk},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["selected_packstreet_id"], self.packstreet_a.pk)

        self.user.refresh_from_db()
        self.assertEqual(self.user.selected_packstreet_id, self.packstreet_a.pk)

    def test_patch_me_sets_show_consumables(self) -> None:
        token = self._login_and_csrf()
        response = self.client.patch(
            "/api/me",
            data={"show_consumables": False},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["show_consumables"])

        self.user.refresh_from_db()
        self.assertFalse(self.user.show_consumables)

    def test_patch_me_sets_both_fields_at_once(self) -> None:
        token = self._login_and_csrf()
        response = self.client.patch(
            "/api/me",
            data={
                "show_consumables": False,
                "selected_packstreet_id": self.packstreet_b.pk,
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["show_consumables"])
        self.assertEqual(data["selected_packstreet_id"], self.packstreet_b.pk)

        self.user.refresh_from_db()
        self.assertFalse(self.user.show_consumables)
        self.assertEqual(self.user.selected_packstreet_id, self.packstreet_b.pk)

    def test_patch_me_can_switch_packstreet(self) -> None:
        self.user.selected_packstreet = self.packstreet_a
        self.user.save()

        token = self._login_and_csrf()
        response = self.client.patch(
            "/api/me",
            data={"selected_packstreet_id": self.packstreet_b.pk},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["selected_packstreet_id"], self.packstreet_b.pk
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.selected_packstreet_id, self.packstreet_b.pk)

    def test_patch_me_returns_persisted_values_on_refresh(self) -> None:
        self.user.selected_packstreet = self.packstreet_a
        self.user.show_consumables = False
        self.user.save()

        token = self._login_and_csrf()
        response = self.client.get("/api/me", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["selected_packstreet_id"], self.packstreet_a.pk)
        self.assertFalse(data["show_consumables"])

    def test_patch_me_invalid_packstreet_returns_404(self) -> None:
        token = self._login_and_csrf()
        response = self.client.patch(
            "/api/me",
            data={"selected_packstreet_id": 99999},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 404)

    def test_patch_me_empty_body_is_noop(self) -> None:
        self.user.selected_packstreet = self.packstreet_a
        self.user.save()

        token = self._login_and_csrf()
        response = self.client.patch(
            "/api/me",
            data={},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["selected_packstreet_id"], self.packstreet_a.pk)

    def test_patch_me_requires_authentication(self) -> None:
        self.client.get("/api/auth/csrf")
        token = self.client.cookies["csrftoken"].value
        response = self.client.patch(
            "/api/me",
            data={"selected_packstreet_id": self.packstreet_a.pk},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 401)

    def test_patch_me_requires_csrf(self) -> None:
        # token = self._login_and_csrf()
        response = self.client.patch(
            "/api/me",
            data={"selected_packstreet_id": self.packstreet_a.pk},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_patch_me_sets_barcode_view(self) -> None:
        token = self._login_and_csrf()
        response = self.client.patch(
            "/api/me",
            data={"barcode_view": True},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["barcode_view"])

        self.user.refresh_from_db()
        self.assertTrue(self.user.barcode_view)
