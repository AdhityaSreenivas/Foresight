import logging
from typing import List
import numpy as np

from django.conf import settings
from apps.incidents.models import Incident, IncidentEmbedding
from ml_engine.bert_encoder import encode_texts

logger = logging.getLogger(__name__)

def generate_and_persist_embeddings(incidents: List[Incident], model_name: str = None, version: str = "v1") -> List[IncidentEmbedding]:
    """
    Batch generate and persist embeddings for a list of incidents.
    Idempotent: skips incidents that already have an embedding for the specified model/version.
    
    Args:
        incidents: List of Incident instances to generate embeddings for.
        model_name: Optional embedding model name (defaults to settings.BERT_MODEL_NAME).
        version: Embedding version identifier (default "v1").
        
    Returns:
        List of newly created IncidentEmbedding instances.
    """
    if not incidents:
        return []

    if model_name is None:
        model_name = getattr(settings, "BERT_MODEL_NAME", "distilbert-base-uncased")

    # Efficient bulk lookup of existing embeddings to guarantee idempotency without N+1 queries
    incident_ids = [inc.id for inc in incidents]
    existing_ids = set(
        IncidentEmbedding.objects.filter(
            incident_id__in=incident_ids,
            embedding_model=model_name,
            embedding_version=version
        ).values_list("incident_id", flat=True)
    )

    incidents_to_process = [inc for inc in incidents if inc.id not in existing_ids]

    if not incidents_to_process:
        logger.info(
            "Idempotency check: all %d incidents already have embeddings (%s, %s). No new generation needed.",
            len(incidents), model_name, version
        )
        return []

    narratives = [
        inc.composite_narrative if inc.composite_narrative and inc.composite_narrative.strip() else " "
        for inc in incidents_to_process
    ]
    
    logger.info(
        "Generating embeddings for %d incidents (model=%s, version=%s)...",
        len(incidents_to_process), model_name, version
    )
    embeddings = encode_texts(narratives, model_name=model_name, batch_size=getattr(settings, "BERT_BATCH_SIZE", 32))

    new_embeddings = []
    for inc, vector in zip(incidents_to_process, embeddings):
        # Convert numpy array to standard Python float list for JSON serialization
        vector_list = [float(v) for v in vector]
        new_embeddings.append(
            IncidentEmbedding(
                incident=inc,
                vector=vector_list,
                embedding_model=model_name,
                embedding_version=version
            )
        )
    
    if new_embeddings:
        created = IncidentEmbedding.objects.bulk_create(new_embeddings, batch_size=500, ignore_conflicts=True)
        logger.info("Persisted %d new embeddings (idempotent ignore_conflicts=True).", len(created))
        return created
    return []
