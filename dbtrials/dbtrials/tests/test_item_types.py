"""Tests for admin-managed item types and their effect on group views."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from dbtrials.models import Cookinggroup, ItemType, Packstreet

User = get_user_model()

ADMIN = "items-admin"
NORMAL = "items-user"
PASSWORD = "items-pass-123"


class ItemTypeTests(TestCase):
    """Item-type CRUD and its propagation to overviews and the stock CSV."""

    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            username=ADMIN, password=PASSWORD, role="admin"
        )
        self.normal = User.objects.create_user(
            username=NORMAL, password=PASSWORD, role="user"
        )
        self.admin_header = f"Bearer {self._bearer(ADMIN)}"
        self.user_header = f"Bearer {self._bearer(NORMAL)}"
        self.packstreet = Packstreet.objects.create(name="Main")

    def _bearer(self, username: str) -> str:
        response = self.client.post(
            "/api/token/pair",
            data={"username": username, "password": PASSWORD},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access"]

    def _create_group(self, name: str, number: str) -> Cookinggroup:
        response = self.client.post(
            "/api/groups",
            data={
                "name": name,
                "group_number": number,
                "packstreet_id": self.packstreet.pk,
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=self.admin_header,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return Cookinggroup.objects.get(name=name)

    # --- CRUD ------------------------------------------------------------

    def test_admin_can_create_list_rename_delete_item_type(self) -> None:
        create = self.client.post(
            "/api/item-types",
            data={"label": "Projector", "item_class": "rentable"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.admin_header,
        )
        self.assertEqual(create.status_code, 201, create.content)
        created = create.json()
        self.assertEqual(created["key"], "projector")
        item_type_id = created["id"]

        rename = self.client.put(
            f"/api/item-types/{item_type_id}",
            data={"label": "Beamer", "item_class": "rentable"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.admin_header,
        )
        self.assertEqual(rename.status_code, 200)
        renamed = rename.json()
        # The label changes but the key (and thus history) stays stable.
        self.assertEqual(renamed["label"], "Beamer")
        self.assertEqual(renamed["key"], "projector")
        self.assertEqual(renamed["item_class"], "rentable")

        delete = self.client.delete(
            f"/api/item-types/{item_type_id}", HTTP_AUTHORIZATION=self.admin_header
        )
        self.assertEqual(delete.status_code, 204)
        self.assertFalse(ItemType.objects.filter(pk=item_type_id).exists())

    def test_normal_user_cannot_create_item_type(self) -> None:
        response = self.client.post(
            "/api/item-types",
            data={"label": "Projector", "item_class": "rentable"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.user_header,
        )
        self.assertEqual(response.status_code, 403)

    def test_duplicate_item_type_conflicts(self) -> None:
        ItemType.objects.create(key="computer", label="Computer", item_class="rentable")
        response = self.client.post(
            "/api/item-types",
            data={"label": "Computer", "item_class": "rentable"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.admin_header,
        )
        self.assertEqual(response.status_code, 409)

    def test_empty_label_is_rejected(self) -> None:
        response = self.client.post(
            "/api/item-types",
            data={"label": "   ", "item_class": "rentable"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.admin_header,
        )
        self.assertEqual(response.status_code, 400)

    def test_cannot_delete_item_type_that_is_rented_out(self) -> None:
        item_type = ItemType.objects.create(
            key="projector", label="Projector", item_class="rentable"
        )
        group = self._create_group("First", "1")
        rent = self.client.post(
            f"/api/groups/{group.pk}/change-quantity",
            data={"item_type": "projector", "quantity": 2, "action": "rent"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.user_header,
        )
        self.assertEqual(rent.status_code, 200, rent.content)

        response = self.client.delete(
            f"/api/item-types/{item_type.pk}", HTTP_AUTHORIZATION=self.admin_header
        )
        self.assertEqual(response.status_code, 409)
        self.assertTrue(ItemType.objects.filter(pk=item_type.pk).exists())

    def test_renting_unknown_item_type_is_rejected(self) -> None:
        group = self._create_group("First", "1")
        response = self.client.post(
            f"/api/groups/{group.pk}/change-quantity",
            data={"item_type": "nonexistent", "quantity": 1, "action": "rent"},
            content_type="application/json",
            HTTP_AUTHORIZATION=self.user_header,
        )
        self.assertEqual(response.status_code, 400)

    # --- Propagation to views -------------------------------------------

    def test_new_item_type_appears_in_overview_and_csv(self) -> None:
        ItemType.objects.create(key="computer", label="Computer", item_class="rentable")
        ItemType.objects.create(
            key="flipchart", label="Flipchart", item_class="rentable"
        )
        ItemType.objects.create(
            key="projector", label="Projector", item_class="rentable"
        )
        group = self._create_group("First", "1")

        overview = self.client.get(
            f"/api/groups/{group.pk}/overview", HTTP_AUTHORIZATION=self.user_header
        )
        self.assertEqual(overview.status_code, 200)
        labels = [item["label"] for item in overview.json()["items"]]
        self.assertIn("Projector", labels)

        csv_response = self.client.get(
            "/api/groups/stock.csv", HTTP_AUTHORIZATION=self.user_header
        )
        self.assertEqual(csv_response.status_code, 200)
        header = csv_response.content.decode().splitlines()[0]
        self.assertEqual(
            header, "Packstraße,Gruppennummer,Gruppenname,Computer,Flipchart,Projector"
        )
