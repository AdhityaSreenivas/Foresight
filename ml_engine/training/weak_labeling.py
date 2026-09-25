"""
PSIF Platform — Deprecated Weak Labeling Module (Eliminated)

Historical Note:
The previous heuristic/weak-label mechanism derived from severity fields
(severity_potential in {'serious', 'fatality'} and severity_actual in {'none', 'first_aid', 'medical_treatment'})
has been completely eliminated from the architecture.

Audit confirmed that former heuristic records were application-generated synthetic/demo data.
Under the clean provenance model:
  1. SYNTHETIC: Artificial/generated records from benchmark datasets.
  2. HUMAN_APPROVED_SYNTHETIC: Synthetic records reviewed and approved by genuine human HSE reviewers.

Severity fields remain contextual incident information but no longer generate pseudo-ground-truth labels.
"""

def compute_heuristic_psif_label(*args, **kwargs):
    raise NotImplementedError(
        "compute_heuristic_psif_label has been eliminated. Severity fields no longer generate "
        "heuristic or weak labels. Use SYNTHETIC benchmark labels or genuine HUMAN_APPROVED_SYNTHETIC reviews."
    )


def label_incident_queryset(*args, **kwargs):
    raise NotImplementedError(
        "label_incident_queryset has been eliminated. The platform does not generate heuristic labels."
    )
