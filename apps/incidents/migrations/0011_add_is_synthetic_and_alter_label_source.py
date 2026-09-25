# Generated for Foresight SIH Clean Provenance Architecture

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('datasets', '0005_dataset_provenance_fields'),
        ('incidents', '0010_incident_is_synthetic_adjudication_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='incident',
            name='is_synthetic',
            field=models.BooleanField(
                db_index=True,
                default=True,
                help_text='True if this incident is artificially generated/synthetic data.'
            ),
        ),
        migrations.AlterField(
            model_name='incident',
            name='psif_label_source',
            field=models.CharField(
                choices=[
                    ('synthetic', 'Synthetic'),
                    ('human_approved_synthetic', 'Human-Approved Synthetic'),
                    ('real_external', 'Real External (Unlabeled)'),
                    ('real_human', 'Real Human'),
                    ('none', 'No Label Available')
                ],
                db_index=True,
                default='none',
                help_text='Indicates the origin and reliability of the PSIF label on this incident.',
                max_length=35
            ),
        ),
    ]
