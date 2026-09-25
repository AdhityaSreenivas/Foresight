# Generated for Foresight SIH Clean Provenance Architecture

from django.db import migrations, models


def set_dataset_provenance(apps, schema_editor):
    Dataset = apps.get_model("datasets", "Dataset")
    for d in Dataset.objects.all():
        if "osha" in d.name.lower():
            d.source_provenance = "REAL_EXTERNAL"
            d.is_synthetic = False
            d.label_semantics = "UNLABELED"
        else:
            d.source_provenance = "SYNTHETIC"
            d.is_synthetic = True
            d.label_semantics = "SYNTHETIC_GENERATED_LABEL"
        d.dataset_version = "1.0"
        d.quality_version = "1.0"
        d.save(update_fields=[
            "source_provenance", "is_synthetic", "label_semantics",
            "dataset_version", "quality_version"
        ])


class Migration(migrations.Migration):

    dependencies = [
        ('datasets', '0004_dataset_current_task_id_dataset_last_heartbeat_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='dataset',
            name='dataset_version',
            field=models.CharField(default='1.0', help_text='Dataset version identifier.', max_length=50),
        ),
        migrations.AddField(
            model_name='dataset',
            name='is_synthetic',
            field=models.BooleanField(default=True, help_text='True if this dataset contains artificially generated records.'),
        ),
        migrations.AddField(
            model_name='dataset',
            name='label_semantics',
            field=models.CharField(
                choices=[
                    ('SYNTHETIC_GENERATED_LABEL', 'Synthetic Generated Label'),
                    ('HUMAN_ADJUDICATED_ON_SYNTHETIC_RECORD', 'Human Adjudicated on Synthetic Record'),
                    ('UNLABELED', 'Unlabeled')
                ],
                default='SYNTHETIC_GENERATED_LABEL',
                help_text='Semantics of the target labels in this dataset.',
                max_length=100
            ),
        ),
        migrations.AddField(
            model_name='dataset',
            name='quality_version',
            field=models.CharField(default='1.0', help_text='Data quality rule version used during screening.', max_length=50),
        ),
        migrations.AddField(
            model_name='dataset',
            name='source_provenance',
            field=models.CharField(
                choices=[
                    ('SYNTHETIC', 'Synthetic'),
                    ('HUMAN_APPROVED_SYNTHETIC', 'Human-Approved Synthetic'),
                    ('REAL_EXTERNAL', 'Real External'),
                    ('REAL_HUMAN', 'Real Human')
                ],
                default='SYNTHETIC',
                help_text='Origin of the records in this dataset.',
                max_length=50
            ),
        ),
        migrations.RunPython(set_dataset_provenance, reverse_code=migrations.RunPython.noop),
    ]
