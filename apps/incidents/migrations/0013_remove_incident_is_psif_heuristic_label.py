# Generated for Foresight SIH Clean Provenance Architecture

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('incidents', '0012_clean_provenance_and_migrate_heuristic'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='incident',
            name='is_psif_heuristic_label',
        ),
    ]
