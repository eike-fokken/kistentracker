"""Tests for packstreets, group search, stock CSV export and rental history."""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from dbtrials.models import Cookinggroup, ItemType, Packstreet

User = get_user_model()

ADMIN = "groups-admin"
NORMAL = "groups-user"
PASSWORD = "groups-pass-123"


class GroupFeatureTests(TestCase):
    """Packstreet management, search, history and CSV export end-to-end."""

    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            username=ADMIN, password=PASSWORD, role="admin"
        )
        self.normal = User.objects.create_user(
            username=NORMAL, password=PASSWORD, role="user"
        )
        self.admin_header = f"Bearer {self._bearer(ADMIN)}"
        self.user_header = f"Bearer {self._bearer(NORMAL)}"

    def _bearer(self, username: str) -> str:
        response = self.client.post(
            "/api/token/pair",
            data={"username": username, "password": PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access"]

    def _create_group(self, name: str, number: str, packstreet_id: int) -> Cookinggroup:
        response = self.client.post(
            "/api/groups",
            data={"name": name, "internal_id": number, "packstreet_id": packstreet_id},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.admin_header,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return Cookinggroup.objects.get(name=name)

    # --- Packstreets -------------------------------------------------------

    def test_admin_can_create_list_rename_delete_packstreet(self) -> None:
        create = self.client.post(
            "/api/packstreets",
            data={"name": "Alpha"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.admin_header,
        )
        self.assertEqual(create.status_code, 201)
        packstreet_id = create.json()["id"]

        listing = self.client.get(
            "/api/packstreets", HTTP_AUTHORIZATION=self.user_header
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual([b["name"] for b in listing.json()], ["Alpha"])

        rename = self.client.put(
            f"/api/packstreets/{packstreet_id}",
            data={"name": "Beta"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.admin_header,
        )
        self.assertEqual(rename.status_code, 200)
        self.assertEqual(rename.json()["name"], "Beta")

        delete = self.client.delete(
            f"/api/packstreets/{packstreet_id}", HTTP_AUTHORIZATION=self.admin_header
        )
        self.assertEqual(delete.status_code, 204)
        self.assertFalse(Packstreet.objects.filter(pk=packstreet_id).exists())

    def test_normal_user_cannot_create_packstreet(self) -> None:
        response = self.client.post(
            "/api/packstreets",
            data={"name": "Nope"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.user_header,
        )
        self.assertEqual(response.status_code, 403)

    def test_duplicate_packstreet_name_conflicts(self) -> None:
        Packstreet.objects.create(name="Alpha")
        response = self.client.post(
            "/api/packstreets",
            data={"name": "Alpha"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.admin_header,
        )
        self.assertEqual(response.status_code, 409)

    def test_cannot_delete_packstreet_with_groups(self) -> None:
        packstreet = Packstreet.objects.create(name="Occupied")
        self._create_group("G", "1", packstreet.pk)
        response = self.client.delete(
            f"/api/packstreets/{packstreet.pk}", HTTP_AUTHORIZATION=self.admin_header
        )
        self.assertEqual(response.status_code, 409)
        self.assertTrue(Packstreet.objects.filter(pk=packstreet.pk).exists())

    # --- Group creation --------------------------------------------------

    def test_create_group_requires_unique_number(self) -> None:
        packstreet = Packstreet.objects.create(name="Main")
        self._create_group("First", "100", packstreet.pk)
        response = self.client.post(
            "/api/groups",
            data={
                "name": "Second",
                "internal_id": "100",
                "packstreet_id": packstreet.pk,
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=self.admin_header,
        )
        self.assertEqual(response.status_code, 409)

    def test_group_summary_includes_packstreet_and_number(self) -> None:
        packstreet = Packstreet.objects.create(name="Main")
        self._create_group("First", "100", packstreet.pk)
        response = self.client.get("/api/groups", HTTP_AUTHORIZATION=self.user_header)
        self.assertEqual(response.status_code, 200)
        group = response.json()[0]
        self.assertEqual(group["internal_id"], "100")
        self.assertEqual(group["packstreet"]["name"], "Main")

    # --- Search & packstreet filter ---------------------------------------

    def test_list_groups_filters_by_packstreet_and_search(self) -> None:
        a = Packstreet.objects.create(name="A")
        b = Packstreet.objects.create(name="B")
        self._create_group("Marketing", "10", a.pk)
        self._create_group("Sales", "20", b.pk)

        by_packstreet = self.client.get(
            f"/api/groups?packstreet_id={a.pk}", HTTP_AUTHORIZATION=self.user_header
        )
        self.assertEqual([g["name"] for g in by_packstreet.json()], ["Marketing"])

        by_name = self.client.get(
            "/api/groups?q=sale", HTTP_AUTHORIZATION=self.user_header
        )
        self.assertEqual([g["name"] for g in by_name.json()], ["Sales"])

        by_number = self.client.get(
            "/api/groups?q=10", HTTP_AUTHORIZATION=self.user_header
        )
        self.assertEqual([g["name"] for g in by_number.json()], ["Marketing"])

    # --- History ---------------------------------------------------------

    def test_history_tracks_cumulative_stock(self) -> None:
        ItemType.objects.create(key="computer", label="Computer", item_class="rentable")
        ItemType.objects.create(
            key="flipchart", label="Flipchart", item_class="rentable"
        )
        packstreet = Packstreet.objects.create(name="Main")
        group = self._create_group("First", "1", packstreet.pk)
        for _ in range(2):
            self.client.post(
                f"/api/groups/{group.pk}/change-quantity",
                data={"item_type": "computer", "quantity": 3, "action": "rent"},
                content_type="application/json",
                HTTP_AUTHORIZATION=self.user_header,
            )
        self.client.post(
            f"/api/groups/{group.pk}/change-quantity",
            data={"item_type": "computer", "quantity": 2, "action": "return"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.user_header,
        )
        response = self.client.get(
            f"/api/groups/{group.pk}/history", HTTP_AUTHORIZATION=self.user_header
        )
        self.assertEqual(response.status_code, 200)
        series = {s["item_type"]: s for s in response.json()["series"]}
        computer_points = series["computer"]["points"]
        self.assertEqual([p["quantity"] for p in computer_points], [3, 6, 4])
        self.assertEqual(series["flipchart"]["points"], [])

    # --- CSV -------------------------------------------------------------

    def test_stock_csv_ordered_by_packstreet_then_number(self) -> None:
        ItemType.objects.create(key="computer", label="Computer", item_class="rentable")
        ItemType.objects.create(
            key="flipchart", label="Flipchart", item_class="rentable"
        )
        a = Packstreet.objects.create(name="Alpha")
        b = Packstreet.objects.create(name="Beta")
        self._create_group("Ten", "B-id", a.pk)
        self._create_group("Two", "A-id", a.pk)
        self._create_group("Five", "A", b.pk)

        response = self.client.get(
            "/api/groups/stock.csv", HTTP_AUTHORIZATION=self.user_header
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        rows = response.content.decode().splitlines()
        self.assertEqual(
            rows[0], "Packstraße,Kochgruppen-ID,Gruppenname,Computer,Flipchart"
        )
        # Alpha before Beta; within Alpha, numeric order 2 before 10.
        self.assertEqual(rows[1].split(",")[:3], ["Alpha", "A-id", "Two"])
        self.assertEqual(rows[2].split(",")[:3], ["Alpha", "B-id", "Ten"])
        self.assertEqual(rows[3].split(",")[:3], ["Beta", "A", "Five"])

    # --- Group update ----------------------------------------------------

    def test_admin_can_update_group_name_number_and_packstreet(self) -> None:
        a = Packstreet.objects.create(name="Alpha")
        b = Packstreet.objects.create(name="Beta")
        group = self._create_group("Old", "1", a.pk)

        response = self.client.put(
            f"/api/groups/{group.pk}",
            data={"name": "New", "internal_id": "2", "packstreet_id": b.pk},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.admin_header,
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["name"], "New")
        self.assertEqual(body["internal_id"], "2")
        self.assertEqual(body["packstreet"]["name"], "Beta")

        group.refresh_from_db()
        self.assertEqual(group.name, "New")
        self.assertEqual(group.internal_id, "2")
        self.assertEqual(group.packstreet_id, b.pk)

    def test_normal_user_cannot_update_group(self) -> None:
        packstreet = Packstreet.objects.create(name="Main")
        group = self._create_group("Old", "1", packstreet.pk)
        response = self.client.put(
            f"/api/groups/{group.pk}",
            data={"name": "New", "internal_id": "2", "packstreet_id": packstreet.pk},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.user_header,
        )
        self.assertEqual(response.status_code, 403)

    def test_update_group_rejects_duplicate_number(self) -> None:
        packstreet = Packstreet.objects.create(name="Main")
        self._create_group("First", "1", packstreet.pk)
        second = self._create_group("Second", "2", packstreet.pk)
        response = self.client.put(
            f"/api/groups/{second.pk}",
            data={
                "name": "Second",
                "internal_id": "1",
                "packstreet_id": packstreet.pk,
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=self.admin_header,
        )
        self.assertEqual(response.status_code, 409)

    # --- CSV import ------------------------------------------------------

    def _import_csv(self, content: str, header: str | None = None):
        upload = SimpleUploadedFile(
            "groups.csv", content.encode("utf-8"), content_type="text/csv"
        )
        return self.client.post(
            "/api/groups/import",
            data={"file": upload},
            HTTP_AUTHORIZATION=header or self.admin_header,
        )

    def test_import_creates_new_groups_and_skips_existing(self) -> None:
        Packstreet.objects.create(name="Alpha")
        self._create_group("Existing", "1", Packstreet.objects.get(name="Alpha").pk)

        csv_content = "name,number,packstraße\n" "Existing,99,Alpha\n" "Fresh,2,Alpha\n"
        response = self._import_csv(csv_content)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual([r["name"] for r in body["created"]], ["Fresh"])
        self.assertEqual([r["name"] for r in body["skipped"]], ["Existing"])
        self.assertEqual(body["errors"], [])
        self.assertTrue(Cookinggroup.objects.filter(name="Fresh").exists())
        # The pre-existing group was left untouched (number unchanged).
        self.assertEqual(Cookinggroup.objects.get(name="Existing").internal_id, "1")

    def test_import_reports_unknown_packstreet_as_error(self) -> None:
        Packstreet.objects.create(name="Alpha")
        response = self._import_csv("Fresh,2,Nowhere\n")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["created"], [])
        self.assertEqual(len(body["errors"]), 1)
        self.assertFalse(Cookinggroup.objects.filter(name="Fresh").exists())

    def test_import_requires_admin(self) -> None:
        Packstreet.objects.create(name="Alpha")
        response = self._import_csv("Fresh,2,Alpha\n", header=self.user_header)
        self.assertEqual(response.status_code, 403)
