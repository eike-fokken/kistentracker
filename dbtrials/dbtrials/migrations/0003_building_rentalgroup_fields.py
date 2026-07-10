import django.db.models.deletion
from django.db import migrations, models


def populate_building_and_number(apps, schema_editor):
    """Backfill required fields on pre-existing groups with placeholders.

    Existing dev rows have no building or group number yet; assign them all a
    single placeholder building and a unique numeric string derived from the
    primary key so the not-null / unique constraints can be applied.
    """
    Building = apps.get_model("dbtrials", "Building")
    RentalGroup = apps.get_model("dbtrials", "RentalGroup")

    groups = list(RentalGroup.objects.all())
    if not groups:
        return

    placeholder, _ = Building.objects.get_or_create(name="Unassigned")
    for group in groups:
        group.building = placeholder
        group.group_number = str(group.pk)
        group.save(update_fields=["building", "group_number"])


def noop_reverse(apps, schema_editor):
    """No data to undo when reversing; the columns are dropped by the schema."""


class Migration(migrations.Migration):

    dependencies = [
        ("dbtrials", "0002_rentalaction"),
    ]

    operations = [
        migrations.CreateModel(
            name="Building",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=100, unique=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="rentalgroup",
            name="group_number",
            field=models.CharField(max_length=50, null=True),
        ),
        migrations.AddField(
            model_name="rentalgroup",
            name="building",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="groups",
                to="dbtrials.building",
            ),
        ),
        migrations.RunPython(populate_building_and_number, noop_reverse),
        migrations.AlterField(
            model_name="rentalgroup",
            name="group_number",
            field=models.CharField(max_length=50, unique=True),
        ),
        migrations.AlterField(
            model_name="rentalgroup",
            name="building",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="groups",
                to="dbtrials.building",
            ),
        ),
    ]
