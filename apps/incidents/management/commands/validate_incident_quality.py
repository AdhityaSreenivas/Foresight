from django.core.management.base import BaseCommand
from apps.incidents.models import Incident, IncidentDataQuality
from apps.incidents.services.data_quality import validate_incident_quality

class Command(BaseCommand):
    help = "Validates source data quality for all incidents"

    def handle(self, *args, **options):
        incidents = Incident.objects.all()
        total = incidents.count()
        self.stdout.write(f"Starting data quality validation for {total} incidents...")
        
        valid = 0
        warning = 0
        critical = 0
        
        for inc in incidents:
            dq = validate_incident_quality(inc)
            if dq.status == IncidentDataQuality.Status.VALID:
                valid += 1
            elif dq.status == IncidentDataQuality.Status.WARNING:
                warning += 1
            elif dq.status == IncidentDataQuality.Status.CRITICAL:
                critical += 1
                
        self.stdout.write(self.style.SUCCESS(f"Validation complete for {total} incidents."))
        self.stdout.write(f"Valid: {valid}")
        self.stdout.write(self.style.WARNING(f"Warning: {warning}"))
        self.stdout.write(self.style.ERROR(f"Critical: {critical}"))
