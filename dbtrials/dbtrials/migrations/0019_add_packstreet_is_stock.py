from django.db import migrations, models


def seed_stock_packstreet(apps, schema_editor):
    Packstreet = apps.get_model("dbtrials", "Packstreet")
    Cookinggroup = apps.get_model("dbtrials", "Cookinggroup")

    stock, _created = Packstreet.objects.get_or_create(
        name="Lager",
        defaults={"is_stock": True},
    )
    Cookinggroup.objects.get_or_create(
        name="Lager",
        defaults={
            "internal_id": "STOCK",
            "packstreet": stock,
        },
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("dbtrials", "0018_add_crate_model"),
    ]

    operations = [
        migrations.AddField(
            model_name="packstreet",
            name="is_stock",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(seed_stock_packstreet, noop_reverse),
    ]