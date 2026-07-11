"""Add selected_packstreet FK to User."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("dbtrials", "0013_rename_group_number_to_internal_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="selected_packstreet",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="dbtrials.packstreet",
            ),
        ),
    ]