from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db.models import (
    CASCADE,
    PROTECT,
    SET_NULL,
    BooleanField,
    CharField,
    DateTimeField,
    ForeignKey,
    IntegerField,
    Model,
    SlugField,
    TextChoices,
    UniqueConstraint,
)
from django.utils import timezone


class UserRole(TextChoices):
    """The access levels an application user can have."""

    USER = "user", "Benutzer"
    ADMIN = "admin", "Administrator"


class UserManager(DjangoUserManager["User"]):
    """User manager that marks superusers as admins by default."""

    def create_superuser(
        self,
        username: str,
        email: str | None = None,
        password: str | None = None,
        **extra_fields: object,
    ) -> "User":
        """Create a superuser, defaulting its role to admin."""
        extra_fields.setdefault("role", UserRole.ADMIN)
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """Application user; admins may access privileged endpoints."""

    role = CharField(
        max_length=10,
        choices=UserRole.choices,
        default=UserRole.USER,
    )

    show_consumables = BooleanField(
        default=True,
    )

    prefer_rent = BooleanField(
        default=True,
    )

    selected_packstreet = ForeignKey(
        "Packstreet",
        null=True,
        blank=True,
        on_delete=SET_NULL,
        related_name="+",
    )

    objects = UserManager()  # type: ignore[misc]

    @property
    def is_admin(self) -> bool:
        """Whether the user holds the admin role."""
        return self.role == UserRole.ADMIN


class ItemClass(TextChoices):
    """The class of an item type — rentable (tracked by count) or consumable."""

    RENTABLE = "rentable", "ausleihbar"
    CONSUMABLE = "consumable", "verbrauchbar"


class ItemType(Model):
    """A kind of item that can be rented out; managed by admins.

    The stable ``key`` (a slug) is what rental and audit-log rows store, so a
    type can be renamed without rewriting history. Types are looked up by key.
    """

    key = SlugField(max_length=50, unique=True)
    label = CharField(max_length=100)
    item_class = CharField(
        max_length=20,
        choices=ItemClass.choices,
    )
    created_at = DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-item_class", "created_at"]

    def __str__(self) -> str:
        return self.label


class ActionType(TextChoices):
    """The kinds of actions recorded in the rental audit log."""

    RENT = "rent", "Ausleihe"
    RETURN = "return", "Rückgabe"
    CORRECT = "correct", "Korrektur"


class Packstreet(Model):
    """A physical packstreet that cooking groups are located in."""

    name = CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Cookinggroup(Model):
    """A user group that is able to rent items."""

    name = CharField(max_length=200, unique=True)
    internal_id = CharField(max_length=50, unique=True)
    packstreet = ForeignKey(
        Packstreet,
        on_delete=PROTECT,
        related_name="groups",
    )

    def __str__(self) -> str:
        return f"{self.internal_id} - {self.name}"


class Rental(Model):
    """The number of a given item type currently rented out to a group."""

    group = ForeignKey(
        Cookinggroup,
        on_delete=CASCADE,
        related_name="rentals",
    )
    item_type = CharField(max_length=50)
    quantity = IntegerField(
        default=0,
    )

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["group", "item_type"],
                name="unique_rental_per_group_and_item_type",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.group.name}: {self.quantity} x {self.item_type}"


class RentalAction(Model):
    """An audit-log entry recording a single rent or return action."""

    group = ForeignKey(
        Cookinggroup,
        on_delete=CASCADE,
        related_name="actions",
    )
    user = ForeignKey(
        User,
        on_delete=SET_NULL,
        null=True,
        related_name="rental_actions",
    )
    action = CharField(max_length=10, choices=ActionType.choices)
    item_type = CharField(max_length=50)
    quantity = IntegerField()
    timestamp = DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        return (
            f"{self.timestamp:%Y-%m-%d %H:%M} {self.action} "
            f"{self.quantity} x {self.item_type} ({self.group.name})"
        )
