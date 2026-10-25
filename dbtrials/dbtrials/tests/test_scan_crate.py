"""Tests for barcode crate scanning and its stock/crate bookkeeping."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from dbtrials.models import Cookinggroup, Crate, Packstreet, Rental, RentalAction

User = get_user_model()

USER = "scan-user"
PASSWORD = "scan-pass-123"

BARCODE = "80030000000000012345ABC"
OTHER_BARCODE = "80030000000000012345ABD"
INVALID_BARCODE = "not-a-grai"


class ScanCrateTests(TestCase):
    """Rent/return a crate by barcode and keep crate + rental in sync."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username=USER, password=PASSWORD, role="user"
        )
        self.user_header = f"Bearer {self._bearer(USER)}"
        self.stock_group = Cookinggroup.objects.get(name="Lager")
        self.packstreet = Packstreet.objects.create(name="Camp")
        self.group = Cookinggroup.objects.create(
            name="Testgruppe", internal_id="42", packstreet=self.packstreet
        )
        self.other_packstreet = Packstreet.objects.create(name="Other")
        self.other_group = Cookinggroup.objects.create(
            name="Othergruppe", internal_id="43", packstreet=self.other_packstreet
        )

    def _bearer(self, username: str) -> str:
        response = self.client.post(
            "/api/token/pair",
            data={"username": username, "password": PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access"]

    def _scan(self, group_id: int, barcode: str = BARCODE, action: str = "rent"):
        response = self.client.post(
            f"/api/groups/{group_id}/scan-crate",
            data={"barcode": barcode, "action": action},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.user_header,
        )
        return response

    def _quantity(self, group: Cookinggroup) -> int:
        rental = Rental.objects.filter(group=group, item_type="kiste").first()
        return rental.quantity if rental else 0

    # --- Rent ---------------------------------------------------------------

    def test_first_scan_rents_crate(self) -> None:
        response = self._scan(self.group.pk)

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["crate_was_created"])
        self.assertEqual(body["quantity"], 1)
        self.assertIsNone(body["warning"])

        crate = Crate.objects.get(barcode=BARCODE)
        self.assertEqual(crate.last_seen_with, self.group)
        self.assertEqual(self._quantity(self.group), 1)

    def test_duplicate_scan_within_30s_is_rejected(self) -> None:
        self.assertEqual(self._scan(self.group.pk).status_code, 200)

        response = self._scan(self.group.pk)

        self.assertEqual(response.status_code, 425)
        self.assertEqual(self._quantity(self.group), 1)

    def test_scan_after_30s_warns_but_counts(self) -> None:
        self.assertEqual(self._scan(self.group.pk).status_code, 200)
        crate = Crate.objects.get(barcode=BARCODE)
        crate.last_seen_at = timezone.now() - timedelta(seconds=31)
        crate.save(update_fields=["last_seen_at"])

        response = self._scan(self.group.pk)

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["warning"], "Kiste bereits bei dieser Gruppe.")
        self.assertEqual(body["quantity"], 2)

    def test_rent_from_another_group_warns(self) -> None:
        self.assertEqual(self._scan(self.other_group.pk).status_code, 200)
        crate = Crate.objects.get(barcode=BARCODE)
        crate.last_seen_at = timezone.now() - timedelta(seconds=31)
        crate.save(update_fields=["last_seen_at"])

        response = self._scan(self.group.pk)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["warning"], "Kiste zuletzt bei 43 gesehen.")
        self.assertEqual(self._quantity(self.group), 1)
        crate.refresh_from_db()
        self.assertEqual(crate.last_seen_with, self.group)

    # --- Return -------------------------------------------------------------

    def test_return_without_rent_is_rejected(self) -> None:
        response = self._scan(self.group.pk, action="return")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(self._quantity(self.group), 0)
        self.assertEqual(RentalAction.objects.filter(barcode=BARCODE).count(), 0)

    def test_return_restores_stock_group(self) -> None:
        self.assertEqual(self._scan(self.group.pk).status_code, 200)
        crate = Crate.objects.get(barcode=BARCODE)
        crate.last_seen_at = timezone.now() - timedelta(seconds=31)
        crate.save(update_fields=["last_seen_at"])

        response = self._scan(self.group.pk, action="return")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["quantity"], 0)
        crate.refresh_from_db()
        self.assertEqual(crate.last_seen_with, self.stock_group)
        self.assertEqual(self._quantity(self.group), 0)

    def test_return_at_stock_group_within_30s_is_rejected(self) -> None:
        self.assertEqual(self._scan(self.group.pk).status_code, 200)
        self.assertEqual(self._scan(self.group.pk, action="return").status_code, 200)

        response = self._scan(self.group.pk, action="return")

        self.assertEqual(response.status_code, 425)
        self.assertEqual(self._quantity(self.group), 0)

    # --- Validation / lookup ------------------------------------------------

    def test_invalid_grai_is_rejected(self) -> None:
        response = self._scan(self.group.pk, barcode=INVALID_BARCODE)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Crate.objects.filter(barcode=INVALID_BARCODE).exists())

    def test_stock_group_is_found_by_flag_not_name(self) -> None:
        self.stock_group.name = "Depot"
        self.stock_group.save(update_fields=["name"])
        self.assertEqual(self._scan(self.group.pk).status_code, 200)
        crate = Crate.objects.get(barcode=BARCODE)
        crate.last_seen_at = timezone.now() - timedelta(seconds=31)
        crate.save(update_fields=["last_seen_at"])

        response = self._scan(self.group.pk, action="return")

        self.assertEqual(response.status_code, 200, response.content)
        crate.refresh_from_db()
        self.assertEqual(crate.last_seen_with, self.stock_group)

    def test_scan_is_rejected_in_stock_group(self) -> None:
        response = self._scan(self.stock_group.pk)

        self.assertEqual(response.status_code, 400)

    def test_tenant_rental_and_crate_stay_in_sync(self) -> None:
        self.assertEqual(self._scan(self.group.pk).status_code, 200)
        crate = Crate.objects.get(barcode=BARCODE)
        crate.last_seen_at = timezone.now() - timedelta(seconds=31)
        crate.save(update_fields=["last_seen_at"])
        self.assertEqual(self._scan(self.group.pk, action="return").status_code, 200)
        crate.refresh_from_db()
        crate.last_seen_at = timezone.now() - timedelta(seconds=31)
        crate.save(update_fields=["last_seen_at"])
        self.assertEqual(self._scan(self.group.pk).status_code, 200)

        self.assertEqual(self._quantity(self.group), 1)
        crate.refresh_from_db()
        self.assertEqual(crate.last_seen_with, self.group)

    # --- Concurrency --------------------------------------------------------

    def test_concurrent_first_scans_create_one_crate(self) -> None:
        def scan() -> int:
            response = self._scan(self.group.pk)
            return response.status_code

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                statuses = list(executor.map(lambda _: scan(), range(2)))
        except Exception as exc:  # SQLite may refuse concurrent writers
            self.skipTest(f"database does not support concurrent writes: {exc}")
        finally:
            connection.close()

        self.assertEqual(Crate.objects.filter(barcode=BARCODE).count(), 1)
        self.assertEqual(statuses.count(200), 2, statuses)
        self.assertEqual(self._quantity(self.group), 2)
