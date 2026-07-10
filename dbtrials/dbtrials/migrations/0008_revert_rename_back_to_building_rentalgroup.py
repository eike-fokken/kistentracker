# Generated manually to revert 0007.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("dbtrials", "0007_rename_building_packstreet_cookinggroup_and_more"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="Packstreet",
            new_name="Building",
        ),
        migrations.RenameModel(
            old_name="Cookinggroup",
            new_name="RentalGroup",
        ),
        migrations.RenameField(
            model_name="RentalGroup",
            old_name="packstreet",
            new_name="building",
        ),
    ]
