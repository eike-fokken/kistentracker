import csv
import io
from datetime import date, datetime, timedelta
from typing import Any

from django.contrib.auth import authenticate as django_authenticate
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError, Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.csrf import ensure_csrf_cookie
from ninja import File, Query
from ninja.errors import HttpError
from ninja.files import UploadedFile
from ninja.security import SessionAuth
from ninja.utils import check_csrf
from ninja_extra import NinjaExtraAPI
from ninja_jwt.authentication import JWTAuth
from ninja_jwt.controller import NinjaJWTDefaultController

from dbtrials.models import (
    ActionType,
    Cookinggroup,
    ItemClass,
    ItemType,
    Packstreet,
    Rental,
    RentalAction,
)
from dbtrials.permissions import (
    AllowAny,
    IsAdmin,
    IsAuthenticated,
    PermissionRouter,
    require_permissions,
)
from dbtrials.schemas import (
    ChangeQuantityIn,
    CookinggroupIn,
    GroupHistoryOut,
    GroupImportResultOut,
    GroupOverviewOut,
    GroupSummaryOut,
    ItemTypeIn,
    ItemTypeOut,
    LoginIn,
    PackstreetIn,
    PackstreetOut,
    RentalActionOut,
    RentalItemOut,
    UpdateActionIn,
    UserOut,
    UserUpdateIn,
)

# from uuid import uuid4


# --- Authentication ------------------------------------------------------
#
# Authentication answers *who are you?* and comes in exactly two flavours. Both
# are offered on every protected endpoint via the `AUTH` list, which ninja
# tries in order and stops at the first that identifies the caller:
#
#   1. Bearer JWT (`JWTAuth`) -- for API consumers / server-to-server clients.
#      The token comes from `POST /api/token/pair`. Because the browser never
#      sends an `Authorization` header ambiently, this transport is not
#      CSRF-relevant and performs *no* CSRF check.
#   2. Django session cookie (`SessionAuth`) -- for browsers (the React SPA).
#      The cookie is set at login and is CSRF-protected: ninja's `SessionAuth`
#      verifies the double-submit token and raises `HttpError(403)` when it is
#      missing or wrong, so the relevant status code is returned automatically.
#
# JWT is listed first so that a request carrying a bearer token is settled by
# `JWTAuth` and never reaches `SessionAuth` -- i.e. token clients are never
# subjected to a CSRF check.
JWT_AUTH = JWTAuth()
SESSION_AUTH = SessionAuth()  # CSRF-enforcing session-cookie auth
AUTH = [JWT_AUTH, SESSION_AUTH]

# Authorization (*what may you do?*) is orthogonal and lives in `permissions`:
# each endpoint declares a policy with `@require_permissions(...)`, enforced by
# `PermissionRouter`. An endpoint that declares nothing is denied for everyone.
#
# Fail closed: every endpoint requires authentication unless it opts out with
# `auth=None` (the token controller and the cookie-auth bootstrap endpoints).
api = NinjaExtraAPI(auth=AUTH)
api.register_controllers(NinjaJWTDefaultController)
router = PermissionRouter()


# --- Helpers -------------------------------------------------------------


def _group_summary(group: Cookinggroup) -> dict[str, Any]:
    rentals = [
        RentalItemOut(item_type=r.item_type, quantity=r.quantity)
        for r in group.rentals.order_by("item_type")
        if ItemType.objects.filter(
            key=r.item_type, item_class=ItemClass.RENTABLE
        ).exists()
    ]
    return {
        "id": group.pk,
        "name": group.name,
        "internal_id": group.internal_id,
        "packstreet": {"id": group.packstreet_id, "name": group.packstreet.name},
        "total_items": sum(r.quantity for r in rentals),
        "rentals": rentals,
    }


def _group_overview(group: Cookinggroup) -> dict[str, Any]:
    quantities = {r.item_type: r.quantity for r in group.rentals.all()}
    items = [
        {
            "item_type": item_type.key,
            "label": item_type.label,
            "item_class": item_type.item_class,
            "quantity": quantities.get(item_type.key, 0),
        }
        for item_type in ItemType.objects.all()
    ]
    recent_actions = [
        {
            "id": action.pk,
            "action": ActionType(action.action),
            "item_type": action.item_type,
            "quantity": action.quantity,
            "username": action.user.get_username() if action.user else None,
            "timestamp": action.timestamp,
        }
        for action in group.actions.select_related("user")[:10]
    ]
    return {
        "id": group.pk,
        "name": group.name,
        "internal_id": group.internal_id,
        "packstreet": {"id": group.packstreet_id, "name": group.packstreet.name},
        "items": items,
        "recent_actions": recent_actions,
    }


# --- Cookie session helpers ----------------------------------------------


def _require_csrf(request: HttpRequest) -> None:
    """Enforce CSRF on cookie endpoints that run without an auth class."""
    if check_csrf(request) is not None:
        raise HttpError(403, "CSRF verification failed.")


# --- Authentication endpoints (browser / cookie flow) --------------------


@router.get("/auth/csrf", auth=None)
@require_permissions(AllowAny)
@ensure_csrf_cookie
def issue_csrf(request: HttpRequest) -> JsonResponse:
    """Set the `csrftoken` cookie so the SPA can send `X-CSRFToken`.

    Returning a real `HttpResponse` lets `@ensure_csrf_cookie` write the cookie
    (with all the attributes configured in settings) on the way out, so we
    don't have to set it by hand.
    """
    return JsonResponse({"detail": "CSRF cookie set."})


@router.post("/auth/login", auth=None, response={200: UserOut})
@require_permissions(AllowAny)
def cookie_login(request: HttpRequest, payload: LoginIn) -> tuple[int, dict[str, Any]]:
    """Browser login: verify credentials and start a Django session.

    CSRF-protected to prevent login CSRF: callers must send a valid
    `X-CSRFToken` header obtained from `GET /api/auth/csrf`.
    """
    _require_csrf(request)
    user = django_authenticate(
        request, username=payload.username, password=payload.password
    )
    if user is None:
        raise HttpError(401, "Ungültiger Benutzername oder Passwort.")
    # `login` cycles the session key and rotates the CSRF token (preventing
    # fixation); `CsrfViewMiddleware` then refreshes the `csrftoken` cookie.
    django_login(request, user)
    return 200, {
        "username": user.get_username(),
        "is_admin": user.is_admin,
        "show_consumables": user.show_consumables,
        "selected_packstreet_id": user.selected_packstreet_id,
    }


@router.post("/auth/logout", auth=None)
@require_permissions(AllowAny)
def cookie_logout(request: HttpRequest) -> dict[str, str]:
    """End the Django session."""
    _require_csrf(request)
    django_logout(request)
    return {"detail": "Abgemeldet."}


# --- Endpoints -----------------------------------------------------------


@router.get(
    "/me",
    response=UserOut,
)
@require_permissions(IsAuthenticated)
def current_user(request: HttpRequest) -> dict[str, Any]:
    """Return the authenticated user's identity and admin status."""
    user = getattr(request, "auth")
    return {
        "username": user.get_username(),
        "is_admin": user.is_admin,
        "show_consumables": user.show_consumables,
        "selected_packstreet_id": user.selected_packstreet_id,
    }


@router.patch(
    "/me",
    response=UserOut,
)
@require_permissions(IsAuthenticated)
def update_user(request: HttpRequest, payload: UserUpdateIn) -> dict[str, Any]:
    """Update the authenticated user's preferences."""
    user = getattr(request, "auth")
    changed: list[str] = []
    if payload.show_consumables is not None:
        user.show_consumables = payload.show_consumables
        changed.append("show_consumables")
    if payload.selected_packstreet_id is not None:
        packstreet = get_object_or_404(Packstreet, pk=payload.selected_packstreet_id)
        user.selected_packstreet = packstreet
        changed.append("selected_packstreet")
    if changed:
        user.save(update_fields=changed)
    return {
        "username": user.get_username(),
        "is_admin": user.is_admin,
        "show_consumables": user.show_consumables,
        "selected_packstreet_id": user.selected_packstreet_id,
    }


@router.get(
    "/packstreets",
    response=list[PackstreetOut],
)
@require_permissions(IsAuthenticated)
def list_packstreets(request: HttpRequest) -> list[Packstreet]:
    """List all packstreets, ordered by name."""
    return list(Packstreet.objects.all())


@router.post(
    "/packstreets",
    response={201: PackstreetOut},
)
@require_permissions(IsAdmin)
def create_packstreet(
    request: HttpRequest, payload: PackstreetIn
) -> tuple[int, Packstreet]:
    """Create a new packstreet. Admin only."""
    name = payload.name.strip()
    if not name:
        raise HttpError(400, "Packstraßenname darf nicht leer sein.")
    if Packstreet.objects.filter(name=name).exists():
        raise HttpError(409, f"Eine Packstraße namens '{name}' existiert bereits.")
    return 201, Packstreet.objects.create(name=name)


@router.put(
    "/packstreets/{packstreet_id}",
    response=PackstreetOut,
)
@require_permissions(IsAdmin)
def rename_packstreet(
    request: HttpRequest, packstreet_id: int, payload: PackstreetIn
) -> Packstreet:
    """Rename an existing packstreet. Admin only."""
    name = payload.name.strip()
    if not name:
        raise HttpError(400, "Packstraßenname darf nicht leer sein.")
    packstreet = get_object_or_404(Packstreet, pk=packstreet_id)
    if Packstreet.objects.filter(name=name).exclude(pk=packstreet_id).exists():
        raise HttpError(409, f"Eine Packstraße namens '{name}' existiert bereits.")
    packstreet.name = name
    packstreet.save(update_fields=["name"])
    return packstreet


@router.delete(
    "/packstreets/{packstreet_id}",
    response={204: None},
)
@require_permissions(IsAdmin)
def delete_packstreet(request: HttpRequest, packstreet_id: int) -> tuple[int, None]:
    """Delete a packstreet. Admin only; blocked while groups still use it."""
    packstreet = get_object_or_404(Packstreet, pk=packstreet_id)
    try:
        packstreet.delete()
    except ProtectedError as exc:
        raise HttpError(
            409,
            "Eine Packstraße mit zugewiesenen Gruppen kann nicht gelöscht werden.",
        ) from exc
    return 204, None


# --- Item types ----------------------------------------------------------


@router.get(
    "/item-types",
    response=list[ItemTypeOut],
)
@require_permissions(IsAuthenticated)
def list_item_types(request: HttpRequest) -> list[ItemType]:
    """List all item types, with rentable items before consumables, each ordered by creation time."""
    return list(ItemType.objects.all())


@router.post(
    "/item-types",
    response={201: ItemTypeOut},
)
@require_permissions(IsAdmin)
def create_item_type(request: HttpRequest, payload: ItemTypeIn) -> tuple[int, ItemType]:
    """Create a new item type. Admin only.

    The stable ``key`` is derived from the label so history stays valid across
    later renames. The ``item_class`` must be one of the valid choices.
    """
    label = payload.label.strip()
    if not label:
        raise HttpError(400, "Artikeltyp-Bezeichnung darf nicht leer sein.")
    if payload.item_class not in ItemClass.values:
        raise HttpError(
            400,
            "Wähle eine Artikel-Klasse aus dem Drop-down-Menü.",
        )
    key = slugify(label)
    if not key:
        raise HttpError(
            400, "Artikeltyp-Bezeichnung muss alphanumerische Zeichen enthalten."
        )
    if ItemType.objects.filter(key=key).exists():
        raise HttpError(409, f"Ein Artikeltyp „{label}“ existiert bereits.")
    if ItemType.objects.filter(label__iexact=label).exists():
        raise HttpError(409, f"Ein Artikeltyp „{label}“ existiert bereits.")
    return 201, ItemType.objects.create(
        key=key, label=label, item_class=payload.item_class
    )


@router.put(
    "/item-types/{item_type_id}",
    response=ItemTypeOut,
)
@require_permissions(IsAdmin)
def rename_item_type(
    request: HttpRequest, item_type_id: int, payload: ItemTypeIn
) -> ItemType:
    """Edit an item type. Admin only; the key (and history) stays unchanged.
    Label and item class can both be updated."""
    label = payload.label.strip()
    if not label:
        raise HttpError(400, "Artikeltyp-Bezeichnung darf nicht leer sein.")
    if payload.item_class not in ItemClass.values:
        raise HttpError(
            400,
            "Wähle eine Artikel-Klasse aus dem Drop-down-Menü.",
        )
    item_type = get_object_or_404(ItemType, pk=item_type_id)
    if ItemType.objects.filter(label__iexact=label).exclude(pk=item_type_id).exists():
        raise HttpError(409, f"Ein Artikeltyp „{label}“ existiert bereits.")
    item_type.label = label
    item_type.item_class = payload.item_class
    item_type.save(update_fields=["label", "item_class"])
    return item_type


@router.delete(
    "/item-types/{item_type_id}",
    response={204: None},
)
@require_permissions(IsAdmin)
def delete_item_type(request: HttpRequest, item_type_id: int) -> tuple[int, None]:
    """Delete an item type. Admin only; blocked while any group has it rented out.

    Past audit-log entries reference the type by key and are left untouched.
    """
    item_type = get_object_or_404(ItemType, pk=item_type_id)
    if Rental.objects.filter(item_type=item_type.key, quantity__gt=0).exists():
        raise HttpError(
            409,
            "Ein Artikeltyp, der von Gruppen noch ausgeliehen ist, kann nicht gelöscht werden.",
        )
    item_type.delete()
    return 204, None


@router.post(
    "/groups",
    response={201: GroupSummaryOut},
)
@require_permissions(IsAdmin)
def create_group(
    request: HttpRequest, payload: CookinggroupIn
) -> tuple[int, dict[str, Any]]:
    """Create a new user group that can rent items. Admin only."""
    name = payload.name.strip()
    internal_id = payload.internal_id.strip()
    if not name:
        raise HttpError(400, "Gruppenname darf nicht leer sein.")
    if not internal_id:
        raise HttpError(400, "Kochgruppen-ID darf nicht leer sein.")
    if Cookinggroup.objects.filter(name=name).exists():
        raise HttpError(409, f"Eine Gruppe namens „{name}“ existiert bereits.")
    if Cookinggroup.objects.filter(internal_id=internal_id).exists():
        raise HttpError(
            409, f"Eine Gruppe mit der ID „{internal_id}“ existiert bereits."
        )
    packstreet = get_object_or_404(Packstreet, pk=payload.packstreet_id)
    try:
        group = Cookinggroup.objects.create(
            name=name, internal_id=internal_id, packstreet=packstreet
        )
    except IntegrityError as exc:
        raise HttpError(
            409, "Dieser Gruppenname oder diese Kochgruppen-ID ist bereits vergeben."
        ) from exc
    return 201, _group_summary(group)


@router.get(
    "/groups",
    response=list[GroupSummaryOut],
)
@require_permissions(IsAuthenticated)
def list_groups(
    request: HttpRequest,
    packstreet_id: int | None = Query(None),
    q: str | None = Query(None),
) -> list[dict[str, Any]]:
    """Overview of groups with their number of rented out items.

    Optionally filtered to a single packstreet (``packstreet_id``) and/or matched
    against a search term (``q``) that is compared against both the group name
    and the group number.
    """
    groups = Cookinggroup.objects.select_related("packstreet").prefetch_related(
        "rentals"
    )
    if packstreet_id is not None:
        groups = groups.filter(packstreet_id=packstreet_id)
    if q:
        term = q.strip()
        if term:
            groups = groups.filter(
                Q(name__icontains=term) | Q(internal_id__icontains=term)
            )
    groups = groups.order_by("packstreet__name", "internal_id", "name")
    return [_group_summary(group) for group in groups]


@router.get(
    "/groups/{group_id}/history",
    response=GroupHistoryOut,
)
@require_permissions(IsAuthenticated)
def group_history(
    request: HttpRequest,
    group_id: int,
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
) -> dict[str, Any]:
    """Cumulative rented-out stock over time, per item type, for a group.

    Replays the rental audit log in chronological order, accumulating a running
    quantity for each item type so the frontend can chart rentals and returns
    over time.  Optional start_date / end_date (inclusive) filter the result
    to a specific time window and insert a synthetic starting point so that
    charts reflect the actual stock at the window start.
    """
    group = get_object_or_404(Cookinggroup, pk=group_id)
    item_types = list(ItemType.objects.all())
    running: dict[str, int] = {it.key: 0 for it in item_types}

    if start_date is not None or end_date is not None:
        # Compute the cumulative quantity at the start of the window (or day 0)
        # so that charts don't falsely start at 0.
        start = (
            start_date
            if start_date is not None
            else datetime(1970, 1, 1, tzinfo=timezone.get_current_timezone())
        )
        end = (
            end_date
            if end_date is not None
            else datetime(2099, 12, 31, tzinfo=timezone.get_current_timezone())
        )
        pre_actions = group.actions.filter(timestamp__lt=start).order_by("timestamp")
        for action in pre_actions:
            item_type = action.item_type
            if item_type not in running:
                continue
            delta = (
                action.quantity
                if action.action == ActionType.RENT
                else -action.quantity
            )
            running[item_type] = running[item_type] + delta
        end_inclusive = end + timedelta(days=1)
        actions = group.actions.filter(
            timestamp__gte=start, timestamp__lt=end_inclusive
        ).order_by("timestamp")
    else:
        actions = group.actions.order_by("timestamp")

    points: dict[str, list[dict[str, Any]]] = {it.key: [] for it in item_types}

    if start_date is not None:
        # Inject a synthetic starting point so the chart includes the
        # correct quantity at the beginning of the window.
        start_dt = datetime.combine(
            start_date, datetime.min.time(), tzinfo=timezone.get_current_timezone()
        )
        for it in item_types:
            points[it.key].append(
                {"timestamp": start_dt, "quantity": running[it.key]}
            )

    for action in actions:
        item_type = action.item_type
        if item_type not in running:
            # Ignore log entries for item types no longer defined.
            continue
        delta = (
            action.quantity if action.action == ActionType.RENT else -action.quantity
        )
        running[item_type] = running[item_type] + delta
        points[item_type].append(
            {"timestamp": action.timestamp, "quantity": running[item_type]}
        )
    series = [
        {
            "item_type": it.key,
            "label": it.label,
            "points": points[it.key],
        }
        for it in item_types
    ]
    return {
        "id": group.pk,
        "name": group.name,
        "internal_id": group.internal_id,
        "series": series,
    }


@router.get(
    "/groups/stock.csv",
)
@require_permissions(IsAuthenticated)
def download_stock_csv(request: HttpRequest) -> HttpResponse:
    """Download current per-group item stock as CSV, ordered by packstreet then number.

    Columns: packstreet, group number, group name, then one column per item type.
    """
    item_types = list(ItemType.objects.all())
    groups = list(
        Cookinggroup.objects.select_related("packstreet").prefetch_related("rentals")
    )

    def sort_key(group: Cookinggroup) -> tuple[str, str, str]:
        return (group.packstreet.name, group.internal_id, group.name)

    groups.sort(key=sort_key)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="gruppen-bestand.csv"'
    writer = csv.writer(response)
    writer.writerow(
        ["Packstraße", "Kochgruppen-ID", "Gruppenname"]
        + [item_type.label for item_type in item_types]
    )
    for group in groups:
        quantities = {r.item_type: r.quantity for r in group.rentals.all()}
        writer.writerow(
            [group.packstreet.name, group.internal_id, group.name]
            + [quantities.get(item_type.key, 0) for item_type in item_types]
        )
    return response


_CSV_HEADER = ("Gruppenname", "Kochgruppen-ID", "Packstraße")


@router.post(
    "/groups/import",
    response={200: GroupImportResultOut},
)
@require_permissions(IsAdmin)
def import_groups(
    request: HttpRequest, file: UploadedFile = File(...)
) -> tuple[int, dict[str, Any]]:
    """Bulk-create groups from a CSV file. Admin only.

    The CSV must include a header row with the exact columns ``Gruppenname``,
    ``Kochgruppen-ID`` and ``Packstraße``. A group whose name or internal ID
    already exists is left untouched and reported under ``skipped``. Rows that
    omit a field or reference an unknown packstreet are reported under
    ``errors``. Packstreets must already exist -- the import never creates them.
    """
    try:
        text = file.read().decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HttpError(
            400, "Die hochgeladene Datei muss eine UTF-8-kodierte CSV-Datei sein."
        ) from exc

    created: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    errors: list[str] = []

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HttpError(400, "Die CSV-Datei enthält keine Daten.")
    fieldnames = [col.strip() for col in reader.fieldnames]

    missing = [req for req in _CSV_HEADER if req not in fieldnames]
    if missing:
        known = ", ".join(fieldnames)
        need = ", ".join(missing)
        raise HttpError(
            400,
            f"Die Kopfzeile der CSV-Datei muss die Spalten {need} enthalten. "
            f"Erkannt wurden: {known}.",
        )

    for row in reader:
        line_number = reader.line_num
        if not any(v.strip() for v in row.values()):
            continue
        name = (row.get("Gruppenname") or "").strip()
        internal_id = (row.get("Kochgruppen-ID") or "").strip()
        packstreet_name = (row.get("Packstraße") or "").strip()
        if not name or not internal_id or not packstreet_name:
            errors.append(
                f"Zeile {line_number}: Gruppenname, Kochgruppen-ID und Packstraße "
                "sind alle erforderlich."
            )
            continue
        packstreet = Packstreet.objects.filter(name__iexact=packstreet_name).first()
        if packstreet is None:
            errors.append(
                f"Zeile {line_number}: unbekannte Packstraße „{packstreet_name}“."
            )
            continue
        row_out = {
            "name": name,
            "internal_id": internal_id,
            "packstreet": packstreet.name,
        }
        if (
            Cookinggroup.objects.filter(name=name).exists()
            or Cookinggroup.objects.filter(internal_id=internal_id).exists()
        ):
            skipped.append(row_out)
            continue
        try:
            with transaction.atomic():
                Cookinggroup.objects.create(
                    name=name, internal_id=internal_id, packstreet=packstreet
                )
        except IntegrityError:
            skipped.append(row_out)
            continue
        created.append(row_out)

    return 200, {"created": created, "skipped": skipped, "errors": errors}


@router.put(
    "/groups/{group_id}",
    response=GroupSummaryOut,
)
@require_permissions(IsAdmin)
def update_group(
    request: HttpRequest, group_id: int, payload: CookinggroupIn
) -> dict[str, Any]:
    """Update a group's name, number and packstreet. Admin only."""
    name = payload.name.strip()
    internal_id = payload.internal_id.strip()
    if not name:
        raise HttpError(400, "Gruppenname darf nicht leer sein.")
    if not internal_id:
        raise HttpError(400, "Kochgruppen-ID darf nicht leer sein.")
    group = get_object_or_404(Cookinggroup, pk=group_id)
    if Cookinggroup.objects.filter(name=name).exclude(pk=group_id).exists():
        raise HttpError(409, f"Eine Gruppe namens „{name}“ existiert bereits.")
    if (
        Cookinggroup.objects.filter(internal_id=internal_id)
        .exclude(pk=group_id)
        .exists()
    ):
        raise HttpError(
            409, f"Eine Gruppe mit der ID „{internal_id}“ existiert bereits."
        )
    packstreet = get_object_or_404(Packstreet, pk=payload.packstreet_id)
    group.name = name
    group.internal_id = internal_id
    group.packstreet = packstreet
    try:
        group.save(update_fields=["name", "internal_id", "packstreet"])
    except IntegrityError as exc:
        raise HttpError(
            409, "Dieser Gruppenname oder diese Kochgruppen-ID ist bereits vergeben."
        ) from exc
    return _group_summary(group)


@router.get(
    "/groups/{group_id}",
    response=GroupSummaryOut,
)
@require_permissions(IsAuthenticated)
def get_group(request: HttpRequest, group_id: int) -> dict[str, Any]:
    """Overview of a single group with its rented out items."""
    group = get_object_or_404(Cookinggroup, pk=group_id)
    return _group_summary(group)


@router.get(
    "/groups/{group_id}/overview",
    response=GroupOverviewOut,
)
@require_permissions(IsAuthenticated)
def group_overview(request: HttpRequest, group_id: int) -> dict[str, Any]:
    """Detailed overview of a group listing every possible item type."""
    group = get_object_or_404(Cookinggroup, pk=group_id)
    return _group_overview(group)


@router.post(
    "/groups/{group_id}/change-quantity",
    response=GroupSummaryOut,
)
@require_permissions(IsAuthenticated)
def change_quantity(
    request: HttpRequest, group_id: int, payload: ChangeQuantityIn
) -> dict[str, Any]:
    """Change the rented-out quantity of an item type for a group.

    The ``action`` field determines the direction and the audit-log entry type:

      - ``RENT`` — add items. ``quantity`` must be positive.
      - ``RETURN`` — remove items. ``quantity`` must be positive. Blocked for
        consumable types.

    """
    group = get_object_or_404(Cookinggroup, pk=group_id)
    if payload.quantity == 0:
        return _group_summary(group)
    item_type = ItemType.objects.filter(key=payload.item_type).first()
    if item_type is None:
        raise HttpError(400, f"Unbekannter Artikeltyp „{payload.item_type}“.")

    if payload.action == ActionType.RENT and payload.quantity < 0:
        raise HttpError(400, "Ausleihe: Menge muss eine positive Zahl sein.")
    if payload.action == ActionType.RETURN and payload.quantity < 0:
        raise HttpError(400, "Rückgabe: Menge muss eine positive Zahl sein.")
    if payload.action not in (ActionType.RENT, ActionType.RETURN):
        raise HttpError(400, "Nur Ausleihe oder Rückgabe ist erlaubt.")
    if (
        payload.action == ActionType.RETURN
        and item_type.item_class == ItemClass.CONSUMABLE
    ):
        raise HttpError(
            400,
            "Verbrauchsartikel können nicht zurückgegeben werden — "
            "sie werden nur ausgegeben.",
        )

    with transaction.atomic():
        if payload.action == ActionType.RENT:
            new_rental, _created = Rental.objects.select_for_update().get_or_create(
                group=group, item_type=payload.item_type
            )
            new_rental.quantity += payload.quantity
            new_rental.save(update_fields=["quantity"])
        else:
            # RETURN: remove items.
            abs_qty = payload.quantity
            existing = (
                Rental.objects.select_for_update()
                .filter(group=group, item_type=payload.item_type)
                .first()
            )
            if existing is not None:
                existing.quantity -= abs_qty
                existing.save(update_fields=["quantity"])
            else:
                Rental.objects.create(
                    group=group,
                    item_type=payload.item_type,
                    quantity=-abs_qty,
                )

        RentalAction.objects.create(
            group=group,
            user=getattr(request, "auth", None),
            action=payload.action,
            item_type=payload.item_type,
            quantity=payload.quantity,
        )
    group.refresh_from_db()
    return _group_summary(group)


@router.get(
    "/groups/{group_id}/recent-actions",
    response=list[RentalActionOut],
)
@require_permissions(IsAuthenticated)
def recent_actions(
    request: HttpRequest,
    group_id: int,
) -> list[dict[str, Any]]:
    """List recent rental actions for the correction/deletion dialog.

    Regular users: always restricted to their own actions from the last
    10 minutes.

    Admins: see all actions from all users for all time. Day filtering
    is handled client-side.
    """
    group = get_object_or_404(Cookinggroup, pk=group_id)
    user = getattr(request, "auth")
    is_admin = getattr(user, "is_admin", False)

    qs = group.actions.select_related("user")

    if is_admin:
        pass
    else:
        cutoff = timezone.now() - timedelta(minutes=10)
        qs = qs.filter(timestamp__gte=cutoff, timestamp__lte=timezone.now())
        qs = qs.filter(user=user)
        qs = qs[:100]

    return [
        {
            "id": action.pk,
            "action": ActionType(action.action),
            "item_type": action.item_type,
            "quantity": action.quantity,
            "username": action.user.get_username() if action.user else None,
            "timestamp": action.timestamp,
        }
        for action in qs
    ]


@router.patch(
    "/groups/{group_id}/actions/{action_id}",
    response=GroupSummaryOut,
)
@require_permissions(IsAuthenticated)
def update_action(
    request: HttpRequest, group_id: int, action_id: int, payload: UpdateActionIn
) -> dict[str, Any]:
    """Update the quantity of a rental action and adjust the group's stock.

    Regular users can only update their own actions within a 10-minute window.
    Admins can update any action regardless of age or ownership.
    The action type (rent/return) cannot be changed — only the quantity.
    """
    group = get_object_or_404(Cookinggroup, pk=group_id)
    action = get_object_or_404(RentalAction, pk=action_id, group=group)
    user = getattr(request, "auth")
    is_admin = getattr(user, "is_admin", False)

    if not is_admin:
        if action.user != user:
            raise HttpError(403, "Du kannst nur deine eigenen Aktionen bearbeiten.")
        cutoff = timezone.now() - timedelta(minutes=10)
        if action.timestamp < cutoff:
            raise HttpError(
                403,
                "Aktionen können nur innerhalb von 10 Minuten bearbeitet werden.",
            )

    with transaction.atomic():
        rental = Rental.objects.select_for_update().get(
            group=group, item_type=action.item_type
        )
        if action.action == ActionType.RENT:
            rental.quantity -= action.quantity
        else:
            rental.quantity += action.quantity
        rental.save(update_fields=["quantity"])

        action.quantity = payload.quantity

        if action.action == ActionType.RENT:
            rental.quantity += action.quantity
        else:
            rental.quantity -= action.quantity
        rental.save(update_fields=["quantity"])

        action.save(update_fields=["quantity"])

    group.refresh_from_db()
    return _group_summary(group)


@router.delete(
    "/groups/{group_id}/actions/{action_id}",
    response=GroupSummaryOut,
)
@require_permissions(IsAuthenticated)
def delete_action(
    request: HttpRequest, group_id: int, action_id: int
) -> dict[str, Any]:
    """Delete a rental action and reverse its effect on the group's stock.

    Regular users can only delete their own actions within a 10-minute window.
    Admins can delete any action regardless of age or ownership.
    """
    group = get_object_or_404(Cookinggroup, pk=group_id)
    action = get_object_or_404(RentalAction, pk=action_id, group=group)
    user = getattr(request, "auth")
    is_admin = getattr(user, "is_admin", False)

    if not is_admin:
        if action.user != user:
            raise HttpError(403, "Du kannst nur deine eigenen Aktionen löschen.")
        cutoff = timezone.now() - timedelta(minutes=10)
        if action.timestamp < cutoff:
            raise HttpError(
                403,
                "Aktionen können nur innerhalb von 10 Minuten gelöscht werden.",
            )

    with transaction.atomic():
        rental = (
            Rental.objects.select_for_update()
            .filter(group=group, item_type=action.item_type)
            .first()
        )
        if rental is not None:
            if action.action == ActionType.RENT:
                rental.quantity -= action.quantity
            else:
                rental.quantity += action.quantity
            rental.save(update_fields=["quantity"])
        action.delete()

    group.refresh_from_db()
    return _group_summary(group)


api.add_router("", router)
