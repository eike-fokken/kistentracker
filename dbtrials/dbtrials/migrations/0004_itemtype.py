from django.db import migrations, models


def noop_forward(apps, schema_editor):
    """No default item types are seeded — admins create them via the API."""


def noop_reverse(apps, schema_editor):
    """Reversing drops the table, so there is no data to undo."""


class Migration(migrations.Migration):

    dependencies = [
        ("dbtrials", "0003_building_rentalgroup_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="ItemType",
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
                ("key", models.SlugField(max_length=50, unique=True)),
                ("label", models.CharField(max_length=100)),
            ],
            options={
                "ordering": ["label"],
            },
        ),
        migrations.AlterField(
            model_name="rental",
            name="item_type",
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name="rentalaction",
            name="item_type",
            field=models.CharField(max_length=50),
        ),
        migrations.RunPython(noop_forward, noop_reverse),
    ]
