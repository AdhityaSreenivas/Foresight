import logging
from django.core.management.base import BaseCommand
from apps.incidents.models import Incident, IncidentEmbedding
from apps.incidents.services.embedding import generate_and_persist_embeddings
from django.conf import settings

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Idempotent backfill of incident embeddings for related incident similarity search."

    def handle(self, *args, **options):
        self.stdout.write("Starting embedding backfill...")
        
        total_incidents = Incident.objects.count()
        already_embedded = IncidentEmbedding.objects.count()
        
        # Get incidents that don't have an embedding
        # We can use the reverse relation "embedding" which is null if it doesn't exist
        missing_qs = Incident.objects.filter(embedding__isnull=True).order_by('id')
        missing_count = missing_qs.count()
        
        self.stdout.write(f"Total incidents: {total_incidents}")
        self.stdout.write(f"Already embedded: {already_embedded}")
        self.stdout.write(f"To process: {missing_count}")
        
        if missing_count == 0:
            self.stdout.write(self.style.SUCCESS("All incidents are already embedded. Nothing to do."))
            return
            
        # Evaluate to a list to avoid issues with shifting querysets
        missing_list = list(missing_qs)
        
        # Process in batches of 500
        batch_size = 500
        processed = 0
        failed = 0
        
        for i in range(0, missing_count, batch_size):
            batch = missing_list[i:i+batch_size]
            try:
                generate_and_persist_embeddings(batch)
                processed += len(batch)
                self.stdout.write(f"Processed {processed}/{missing_count}...")
            except Exception as e:
                failed += len(batch)
                self.stdout.write(self.style.ERROR(f"Batch failed: {str(e)}"))
                logger.error("Failed to generate embeddings for batch", exc_info=True)
                
        self.stdout.write(self.style.SUCCESS(f"Backfill complete."))
        self.stdout.write(f"Total incidents: {total_incidents}")
        self.stdout.write(f"Already embedded: {already_embedded}")
        self.stdout.write(f"New embeddings: {processed}")
        self.stdout.write(f"Failed: {failed}")
