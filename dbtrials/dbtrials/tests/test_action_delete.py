"""Tests for barcode reconciliation when deleting rental actions."""

from datetime import UTC, datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from dbtrials.models import ActionType, Cookinggroup, Crate, Packstreet, RentalAction

User = get_user_model()

ADMIN = "delete-admin"
PASSWORD = "delete-pass-123"

BARCODE_1 = "80030000000000012345ABC"
BARCODE_2 = "80030000000000012345ABD"


class DeleteActionBarcodeTests(TestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            username=ADMIN, password=PASSWORD, role="admin"
        )
        self.admin_header = f"Bearer {self._bearer(ADMIN)}"
        self.stock_group = Cookinggroup.objects.get(name="Lager")
        self.packstreet = Packstreet.objects.create(name="Camp")
        self.group = Cookinggroup.objects.create(
            name="Testgruppe", internal_id="42", packstreet=self.packstreet
        )

    def _bearer(self, username: str) -> str:
        response = self.client.post(
            "/api/token/pair",
            data={"username": username, "password": PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access"]

    def _scan(self, group_id: int, barcode: str, action: str) -> None:
        response = self.client.post(
            f"/api/groups/{group_id}/scan-crate",
            data={"barcode": barcode, "action": action},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.admin_header,
        )
        self.assertEqual(response.status_code, 200, response.content)

    def _action(self, barcode: str, action: ActionType | None = None) -> RentalAction:
        qs = RentalAction.objects.filter(barcode=barcode, deleted_at__isnull=True)
        if action is not None:
            qs = qs.filter(action=action)
        latest_action = qs.order_by("-timestamp").first()
        assert latest_action is not None
        return latest_action

    def _delete(self, action_id: int) -> None:
        response = self.client.delete(
            f"/api/groups/{self.group.pk}/actions/{action_id}",
            HTTP_AUTHORIZATION=self.admin_header,
        )
        self.assertEqual(response.status_code, 200, response.content)

    # --- No previous action: revert to stock at first-ever timestamp -------

    def test_delete_only_action_reverts_to_stock_at_marker_date(self) -> None:
        self._scan(self.group.pk, BARCODE_1, "rent")
        action = self._action(BARCODE_1)
        crate = Crate.objects.get(barcode=BARCODE_1)
        self.assertEqual(crate.last_seen_with, self.group)

        self._delete(action.pk)

        crate.refresh_from_db()
        self.assertEqual(crate.last_seen_with, self.stock_group)
        self.assertEqual(crate.last_seen_at, datetime(1900, 1, 1, tzinfo=UTC))

    # --- Previous action exists: replay its state ---------------------------

    def test_delete_take_back_replays_previous_rent_state(self) -> None:
        self._scan(self.group.pk, BARCODE_1, "rent")
        rent_action = self._action(BARCODE_1, ActionType.RENT)
        self._scan(self.group.pk, BARCODE_1, "return")
        return_action = self._action(BARCODE_1, ActionType.RETURN)
        crate = Crate.objects.get(barcode=BARCODE_1)
        self.assertEqual(crate.last_seen_with, self.stock_group)

        self._delete(return_action.pk)

        crate.refresh_from_db()
        self.assertEqual(crate.last_seen_with, self.group)
        self.assertEqual(crate.last_seen_at, rent_action.timestamp)

    def test_delete_rent_replays_previous_return_state(self) -> None:
        self._scan(self.group.pk, BARCODE_1, "rent")
        self._scan(self.group.pk, BARCODE_1, "return")
        return_action = self._action(BARCODE_1, ActionType.RETURN)
        self._scan(self.group.pk, BARCODE_1, "rent")
        rent_action = self._action(BARCODE_1, ActionType.RENT)
        crate = Crate.objects.get(barcode=BARCODE_1)
        self.assertEqual(crate.last_seen_with, self.group)

        self._delete(rent_action.pk)

        crate.refresh_from_db()
        self.assertEqual(crate.last_seen_with, self.stock_group)
        self.assertEqual(crate.last_seen_at, return_action.timestamp)

    # --- Later action exists: leave crate unchanged --------------------------

    def test_delete_keeps_assignment_when_later_action_references_barcode(self) -> None:
        self._scan(self.group.pk, BARCODE_1, "rent")
        rent_action = self._action(BARCODE_1, ActionType.RENT)
        self._scan(self.group.pk, BARCODE_1, "return")
        crate = Crate.objects.get(barcode=BARCODE_1)
        expected_seen_with = crate.last_seen_with
        expected_seen_at = crate.last_seen_at
        self.assertEqual(crate.last_seen_with, self.stock_group)

        self._delete(rent_action.pk)

        crate.refresh_from_db()
        self.assertEqual(crate.last_seen_with, expected_seen_with)
        self.assertEqual(crate.last_seen_at, expected_seen_at)

    # --- Later but deleted action ------------------------------------------

    def test_delete_reverts_when_later_action_is_itself_deleted(self) -> None:
        self._scan(self.group.pk, BARCODE_1, "rent")
        rent_action = self._action(BARCODE_1, ActionType.RENT)
        self._scan(self.group.pk, BARCODE_1, "return")
        return_action = self._action(BARCODE_1, ActionType.RETURN)
        self._delete(return_action.pk)

        crate = Crate.objects.get(barcode=BARCODE_1)
        self.assertEqual(crate.last_seen_with, self.group)
        self.assertEqual(crate.last_seen_at, rent_action.timestamp)

        self._delete(rent_action.pk)

        crate.refresh_from_db()
        self.assertEqual(crate.last_seen_with, self.stock_group)
        self.assertEqual(crate.last_seen_at, datetime(1900, 1, 1, tzinfo=UTC))

    # --- Missing crate ------------------------------------------------------

    def test_delete_succeeds_when_crate_does_not_exist(self) -> None:
        self._scan(self.group.pk, BARCODE_2, "rent")
        action = self._action(BARCODE_2)
        Crate.objects.all().delete()

        self._delete(action.pk)

        action.refresh_from_db()
        self.assertIsNotNone(action.deleted_at)
        self.assertFalse(Crate.objects.filter(barcode=BARCODE_2).exists())
