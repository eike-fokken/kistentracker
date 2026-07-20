from django.db import migrations


def seed_kiste(apps, schema_editor):
    ItemType = apps.get_model("dbtrials", "ItemType")
    ItemType.objects.get_or_create(
        key="kiste",
        defaults={
            "label": "Kiste",
            "item_class": "rentable",
        },
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("dbtrials", "0019_add_packstreet_is_stock"),
    ]

    operations = [
        migrations.RunPython(seed_kiste, noop_reverse),
    ]