"""Rename group_number to internal_id on Cookinggroup."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("dbtrials", "0012_add_user_show_consumables"),
    ]

    operations = [
        migrations.RenameField(
            model_name="cookinggroup",
            old_name="group_number",
            new_name="internal_id",
        ),
    ]