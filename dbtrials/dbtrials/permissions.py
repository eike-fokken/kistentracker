"""Authorization layer: declarative, per-endpoint permission policies.

Authentication (*who are you?*) is handled by the auth classes wired up in
[api.py][dbtrials.api]; authorization (*what are you allowed to do?*) lives
here. The two are orthogonal: the very same permission policy applies whether
a caller arrived with a browser session cookie or a bearer JWT.

Every endpoint must declare its policy with ``@require_permissions(...)``.
Endpoints that forget to do so are denied for *everyone* with a descriptive
error -- access is fail-closed by construction (see :class:`PermissionRouter`).
Use :class:`AllowAny` to deliberately make an endpoint public.
"""

import functools
from typing import Any, Callable, List, Optional, Tuple, TypeVar, Union

from django.http import HttpRequest
from ninja import Router
from ninja.errors import HttpError

CallableT = TypeVar("CallableT", bound=Callable[..., Any])

# A permission may be declared as a class (instantiated lazily) or instance.
PermissionSpec = Union["BasePermission", type["BasePermission"]]

# Attribute under which a view's declared permission policy is stashed.
_PERMS_ATTR = "_dbtrials_required_permissions"


class BasePermission:
    """A single authorization rule, checked against the request and its user."""

    #: HTTP status raised when this rule denies access.
    code: int = 403
    #: Human-readable reason returned to the caller when denied.
    message: str = "You do not have permission to perform this action."

    def has_permission(self, request: HttpRequest, user: Any) -> bool:
        """Return ``True`` to allow the request, ``False`` to deny it."""
        raise NotImplementedError


class AllowAny(BasePermission):
    """Grant access to everyone, including unauthenticated callers."""

    def has_permission(self, request: HttpRequest, user: Any) -> bool:
        return True


class IsAuthenticated(BasePermission):
    """Require any authenticated user (session cookie or bearer token)."""

    code = 401
    message = "Authentication required."

    def has_permission(self, request: HttpRequest, user: Any) -> bool:
        return user is not None and getattr(user, "is_authenticated", False)


class IsAdmin(BasePermission):
    """Require an authenticated user that holds the admin role."""

    message = "Admin privileges required."

    def has_permission(self, request: HttpRequest, user: Any) -> bool:
        return getattr(user, "is_admin", False)


def require_permissions(
    *permissions: PermissionSpec,
) -> Callable[[CallableT], CallableT]:
    """Declare the permission policy required to access an endpoint.

    Permissions may be given as classes (e.g. ``IsAdmin``) or instances; at
    least one must be supplied. An empty policy is a programming error -- use
    :class:`AllowAny` to make an endpoint deliberately public. All listed
    permissions must pass (logical AND).
    """
    if not permissions:
        raise ValueError(
            "require_permissions() needs at least one permission; "
            "use AllowAny to make an endpoint public."
        )
    resolved = tuple(p() if isinstance(p, type) else p for p in permissions)

    def decorator(view_func: CallableT) -> CallableT:
        setattr(view_func, _PERMS_ATTR, resolved)
        return view_func

    return decorator


def _resolve_user(request: HttpRequest) -> Any:
    """The authenticated principal, regardless of which transport set it.

    Authenticated endpoints expose the user as ``request.auth``; ``auth=None``
    endpoints don't, so fall back to Django's ``request.user``.
    """
    user = getattr(request, "auth", None)
    if user is None:
        user = getattr(request, "user", None)
    return user


def _enforce(
    request: HttpRequest, permissions: Optional[Tuple[BasePermission, ...]]
) -> None:
    """Run a view's declared policy, raising :class:`HttpError` on denial."""
    if permissions is None:
        # The view forgot to declare a policy: deny everyone, loudly.
        raise HttpError(
            500,
            "Endpoint misconfigured: no permission policy declared. Decorate "
            "the view with @require_permissions(...) (AllowAny for public).",
        )
    user = _resolve_user(request)
    for permission in permissions:
        if not permission.has_permission(request, user):
            raise HttpError(permission.code, permission.message)


class PermissionRouter(Router):
    """A :class:`~ninja.Router` that enforces a permission policy everywhere.

    Every operation registered on this router is wrapped so that, before the
    view runs, its declared policy (from ``@require_permissions``) is checked.
    Operations without a declared policy are denied for everyone, which makes
    authorization fail-closed by default rather than fail-open.
    """

    def add_api_operation(
        self,
        path: str,
        methods: List[str],
        view_func: Callable,
        **kwargs: Any,
    ) -> None:
        super().add_api_operation(path, methods, self._guard(view_func), **kwargs)

    @staticmethod
    def _guard(view_func: Callable[..., Any]) -> Callable[..., Any]:
        """Wrap ``view_func`` so its permission policy runs before the body."""
        permissions = getattr(view_func, _PERMS_ATTR, None)

        @functools.wraps(view_func)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
            _enforce(request, permissions)
            return view_func(request, *args, **kwargs)

        return wrapper
