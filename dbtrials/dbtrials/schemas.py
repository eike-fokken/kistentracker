from datetime import datetime

from ninja import Schema

from dbtrials.models import ActionType


class UserOut(Schema):
    """Output schema describing the authenticated user."""

    username: str
    is_admin: bool
    show_consumables: bool
    selected_packstreet_id: int | None


class UserUpdateIn(Schema):
    """Input schema for updating user preferences."""

    show_consumables: bool | None = None
    selected_packstreet_id: int | None = None


class LoginIn(Schema):
    """Credentials for the cookie-based browser login."""

    username: str
    password: str


class PackstreetIn(Schema):
    """Input schema for creating or renaming a packstreet."""

    name: str


class PackstreetOut(Schema):
    """Output schema describing a packstreet."""

    id: int
    name: str


class ItemTypeIn(Schema):
    """Input schema for creating or renaming an item type."""

    label: str
    item_class: str


class ItemTypeOut(Schema):
    """Output schema describing an admin-managed item type."""

    id: int
    key: str
    label: str
    item_class: str
    created_at: datetime


class CookinggroupIn(Schema):
    """Input schema for creating or updating a rental group."""

    name: str
    internal_id: str
    packstreet_id: int


class GroupImportRowOut(Schema):
    """A single group row processed during a CSV import."""

    name: str
    internal_id: str
    packstreet: str


class GroupImportResultOut(Schema):
    """Summary of a bulk group CSV import.

    ``created`` lists the newly inserted groups, ``skipped`` the ones whose name
    or number already existed (left untouched), and ``errors`` the rows that
    could not be processed at all.
    """

    created: list[GroupImportRowOut]
    skipped: list[GroupImportRowOut]
    errors: list[str]


class RentActionIn(Schema):
    """Input schema for renting a quantity of an item type."""

    item_type: str
    quantity: int


class ChangeQuantityIn(Schema):
    """Input schema for renting or returning an item type in a group.

    ``action`` determines the direction:
      - ``RENT`` — add items. ``quantity`` must be positive.
      - ``RETURN`` — remove items. ``quantity`` must be positive.
    """

    item_type: str
    quantity: int
    action: ActionType


class RentalItemOut(Schema):
    """Output schema representing a rented item type and its quantity."""

    item_type: str
    quantity: int


class GroupSummaryOut(Schema):
    """Output schema summarizing a rental group and its rentals."""

    id: int
    name: str
    internal_id: str
    packstreet: PackstreetOut
    total_items: int
    rentals: list[RentalItemOut]


class GroupOverviewItemOut(Schema):
    """An item type and how many the group has rented out (0 if none)."""

    item_type: str
    label: str
    item_class: str
    quantity: int


class RentalActionOut(Schema):
    """A single entry from the rental audit log."""

    id: int
    action: ActionType
    item_type: str
    quantity: int
    username: str | None
    timestamp: datetime


class UpdateActionIn(Schema):
    """Input schema for updating a rental action's quantity."""

    quantity: int

class GroupOverviewOut(Schema):
    """Detailed group overview listing every possible item type."""

    id: int
    name: str
    internal_id: str
    packstreet: PackstreetOut
    items: list[GroupOverviewItemOut]
    recent_actions: list[RentalActionOut]


class HistoryPointOut(Schema):
    """A single point in an item type's stock-over-time series."""

    timestamp: datetime
    quantity: int


class ItemHistoryOut(Schema):
    """The cumulative rented-out stock over time for one item type."""

    item_type: str
    label: str
    points: list[HistoryPointOut]


class GroupHistoryOut(Schema):
    """A group's stock-over-time series for every item type."""

    id: int
    name: str
    internal_id: str
    series: list[ItemHistoryOut]
