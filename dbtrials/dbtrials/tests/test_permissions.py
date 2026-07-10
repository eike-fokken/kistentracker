"""Tests for the declarative, fail-closed authorization (permission) layer.

Authorization is orthogonal to the auth transport, so these tests exercise the
permission policies independently of how the caller authenticated.
"""

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.test import Client, TestCase
from ninja.errors import HttpError

from dbtrials.models import Packstreet
from dbtrials.permissions import (
    AllowAny,
    IsAdmin,
    IsAuthenticated,
    PermissionRouter,
    require_permissions,
)

User = get_user_model()

ADMIN = "perm-admin"
NORMAL = "perm-user"
PASSWORD = "perm-pass-123"


class PolicyDeclarationTests(TestCase):
    """`require_permissions` declarations and their enforcement primitives."""

    def test_empty_policy_is_rejected_at_declaration(self) -> None:
        with self.assertRaises(ValueError):

            @require_permissions()
            def _view(request: HttpRequest) -> None:  # pragma: no cover
                return None

    def test_classes_and_instances_are_both_accepted(self) -> None:
        @require_permissions(IsAdmin, IsAuthenticated())
        def view(request: HttpRequest) -> None:  # pragma: no cover
            return None

        policy = getattr(view, "_dbtrials_required_permissions")
        self.assertEqual(len(policy), 2)
        self.assertTrue(all(hasattr(p, "has_permission") for p in policy))

    def test_undeclared_endpoint_is_denied_for_everyone(self) -> None:
        """A view registered without a policy fails closed at request time."""
        router = PermissionRouter()

        @router.get("/no-policy", auth=None)
        def no_policy(request: HttpRequest) -> dict[str, str]:
            return {"detail": "should never run"}

        # The router wraps the view; invoking the wrapped view raises 500.
        wrapped = router.path_operations["/no-policy"].operations[0].view_func
        request = HttpRequest()
        with self.assertRaises(HttpError) as ctx:
            wrapped(request)
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("no permission policy", str(ctx.exception).lower())


class PermissionRuleTests(TestCase):
    """The individual permission rules' allow/deny decisions."""

    anon = SimpleNamespace(is_authenticated=False, is_admin=False)
    normal = SimpleNamespace(is_authenticated=True, is_admin=False)
    admin = SimpleNamespace(is_authenticated=True, is_admin=True)

    def setUp(self) -> None:
        self.request = HttpRequest()

    def test_allow_any_grants_everyone(self) -> None:
        rule = AllowAny()
        self.assertTrue(rule.has_permission(self.request, None))
        self.assertTrue(rule.has_permission(self.request, self.anon))

    def test_is_authenticated(self) -> None:
        rule = IsAuthenticated()
        self.assertEqual(rule.code, 401)
        self.assertFalse(rule.has_permission(self.request, None))
        self.assertFalse(rule.has_permission(self.request, self.anon))
        self.assertTrue(rule.has_permission(self.request, self.normal))

    def test_is_admin(self) -> None:
        rule = IsAdmin()
        self.assertEqual(rule.code, 403)
        self.assertFalse(rule.has_permission(self.request, self.normal))
        self.assertTrue(rule.has_permission(self.request, self.admin))


class EndpointAuthorizationTests(TestCase):
    """End-to-end: real endpoints enforce their declared policy."""

    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            username=ADMIN, password=PASSWORD, role="admin"
        )
        self.normal = User.objects.create_user(
            username=NORMAL, password=PASSWORD, role="user"
        )
        self.packstreet = Packstreet.objects.create(name="Perm Packstreet")

    def _group_payload(self, name: str, number: str) -> dict[str, object]:
        return {
            "name": name,
            "group_number": number,
            "packstreet_id": self.packstreet.pk,
        }

    def _bearer(self, username: str) -> str:
        response = self.client.post(
            "/api/token/pair",
            data={"username": username, "password": PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access"]

    def test_admin_only_endpoint_forbidden_for_normal_user(self) -> None:
        token = self._bearer(NORMAL)
        response = self.client.post(
            "/api/groups",
            data=self._group_payload("G-perm", "1"),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Admin privileges required.")

    def test_admin_only_endpoint_allowed_for_admin(self) -> None:
        token = self._bearer(ADMIN)
        response = self.client.post(
            "/api/groups",
            data=self._group_payload("G-perm", "2"),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 201)

    def test_authenticated_endpoint_allowed_for_normal_user(self) -> None:
        token = self._bearer(NORMAL)
        response = self.client.get("/api/groups", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(response.status_code, 200)

    def test_policy_applies_regardless_of_transport(self) -> None:
        """The same admin-only policy denies a normal user over session auth."""
        client = Client(enforce_csrf_checks=True)
        client.get("/api/auth/csrf")
        token = client.cookies["csrftoken"].value
        client.post(
            "/api/auth/login",
            data={"username": NORMAL, "password": PASSWORD},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        token = client.cookies["csrftoken"].value
        response = client.post(
            "/api/groups",
            data=self._group_payload("G-session", "3"),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Admin privileges required.")
