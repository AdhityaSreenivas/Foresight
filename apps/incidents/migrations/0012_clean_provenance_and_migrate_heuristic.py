# Generated for Foresight SIH Clean Provenance Architecture

from django.db import migrations


def clean_provenance_and_migrate_heuristic(apps, schema_editor):
    Incident = apps.get_model("incidents", "Incident")
    Dataset = apps.get_model("datasets", "Dataset")
    
    # 1. Reclassify OSHA external dataset incidents (3,268 records)
    osha_datasets = Dataset.objects.filter(name__icontains="osha")
    if osha_datasets.exists():
        Incident.objects.filter(dataset__in=osha_datasets).update(
            is_synthetic=False,
            psif_label_source="real_external",
        )

    # 2. Reclassify 9 genuine human-reviewed incidents
    Incident.objects.filter(
        psif_label_source="human",
        is_synthetic_adjudication=False,
    ).update(
        is_synthetic=True,
        psif_label_source="human_approved_synthetic",
    )

    # 3. Reclassify synthetic review simulations
    Incident.objects.filter(
        is_synthetic_adjudication=True,
    ).update(
        is_synthetic=True,
        psif_label_source="synthetic",
    )

    # 4. Reclassify former heuristic records as synthetic (765 records)
    heuristic_qs = Incident.objects.filter(psif_label_source="heuristic")
    for inc in heuristic_qs.iterator(chunk_size=500):
        inc.is_synthetic = True
        inc.psif_label_source = "synthetic"
        # Preserve benchmark label in raw_row for SEED records
        raw = dict(inc.raw_row or {})
        if "sif_label" not in raw and inc.is_psif_heuristic_label is not None:
            raw["sif_label"] = 1 if inc.is_psif_heuristic_label else 0
            raw["synthetic"] = True
            inc.raw_row = raw
        inc.save(update_fields=["is_synthetic", "psif_label_source", "raw_row"])

    # 5. Update historical ModelVersion records
    try:
        ModelVersion = apps.get_model("predictions", "ModelVersion")
        for mv in ModelVersion.objects.all():
            m = dict(mv.metrics or {})
            if m.get("training_source") == "HEURISTIC":
                m["training_source"] = "SYNTHETIC"
                m["historical_training_source"] = "HEURISTIC"
                m["provenance_audit_note"] = (
                    "Trained on previously classified heuristic data that was "
                    "subsequently determined to be synthetic/application-generated demonstration data."
                )
                m["validation_basis"] = "SYNTHETIC DATASET EVALUATION"
                mv.metrics = m
                mv.save(update_fields=["metrics"])
    except Exception:
        pass


class Migration(migrations.Migration):

    dependencies = [
        ('incidents', '0011_add_is_synthetic_and_alter_label_source'),
    ]

    operations = [
        migrations.RunPython(
            clean_provenance_and_migrate_heuristic,
            reverse_code=migrations.RunPython.noop
        ),
    ]
