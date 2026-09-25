import logging
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.incidents.models import Incident, IOGPRuleTag
from apps.predictions.iogp_classifier import classify_iogp_rules

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Idempotent backfill of IOGP Rule tags for all incidents."

    def handle(self, *args, **options):
        self.stdout.write("Starting IOGP Rule Tag backfill...")

        incidents_processed = 0
        tags_created = 0
        tags_removed = 0
        no_match_count = 0
        errors = 0

        # We will delete existing tags created by the same classifier version to ensure idempotency.
        # Currently, all tags use 'iogp_rules_v1'
        classifier_version = "iogp_rules_v1"
        
        # Batch query incidents
        incidents = Incident.objects.all().iterator(chunk_size=1000)

        for incident in incidents:
            try:
                with transaction.atomic():
                    # Idempotent cleanup: remove previous tags from the same version
                    deleted_count, _ = IOGPRuleTag.objects.filter(
                        incident=incident, 
                        classifier_version=classifier_version
                    ).delete()
                    tags_removed += deleted_count

                    fields_to_check = {
                        "description": incident.description,
                        "job_task": incident.job_task,
                        "equipment_involved": incident.equipment_involved,
                        "immediate_cause": incident.immediate_cause,
                        "corrective_actions": incident.corrective_actions,
                        "location": incident.location,
                        "composite_narrative": incident.composite_narrative
                    }

                    iogp_results = classify_iogp_rules(fields_to_check)
                    
                    if not iogp_results:
                        no_match_count += 1
                    else:
                        tags_to_create = []
                        for res in iogp_results:
                            tags_to_create.append(IOGPRuleTag(
                                incident=incident,
                                rule=res["rule"],
                                matched_keywords=res["matched_keywords"],
                                matched_fields=res["matched_fields"],
                                classification_method=res["classification_method"],
                                classifier_version=res["classifier_version"],
                                confidence=res["confidence"]
                            ))
                        IOGPRuleTag.objects.bulk_create(tags_to_create)
                        tags_created += len(tags_to_create)

                    incidents_processed += 1

            except Exception as e:
                logger.error(f"Error processing incident {incident.id}: {e}")
                errors += 1

        self.stdout.write(self.style.SUCCESS("Backfill complete!"))
        self.stdout.write(f"Incidents processed: {incidents_processed}")
        self.stdout.write(f"Tags removed/replaced: {tags_removed}")
        self.stdout.write(f"Tags created: {tags_created}")
        self.stdout.write(f"Incidents with no rule match: {no_match_count}")
        self.stdout.write(f"Errors: {errors}")
