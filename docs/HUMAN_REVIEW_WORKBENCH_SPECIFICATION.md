# Foresight Human Review & Adjudication Workbench Specification
**Document ID:** `SPEC-HSE-HUMAN-REVIEW-V1`  
**Version:** `1.0.0`  
**Status:** `Approved & Implemented`  
**Author:** Foresight Core Safety Engineering & Intelligence Systems  

---

## 1. Executive Summary & Objective

The **Human Review & Adjudication Workbench** establishes a genuine, human-in-the-loop Health, Safety, and Environment (HSE) review infrastructure for Foresight. In high-hazard industrial environments (oil & gas, chemical, petrochemical, heavy construction), automated machine learning models and deterministic rule engines cannot replace licensed HSE practitioners; they exist to highlight potential precursor signals, structure evidence, and eliminate cognitive fatigue.

This system guarantees:
1. **Model / Human Independence**: Human adjudication records are preserved separately from automated predictions. A human review never overwrites statistical model outputs (`prediction.psif_predicted`, `prediction.psif_score`), model versions, or deterministic rule decisions.
2. **Canonical 3-State Decisions**: Exactly three decisions are permitted: `PSIF`, `NOT_PSIF`, and `INSUFFICIENT_INFORMATION`.
3. **Mandatory Domain Rationale**: Reviewers must provide substantive justification ($\ge 10$ characters) explaining *why* an incident is a precursor, why it was interrupted, or why available documentation is inadequate.
4. **Independent & Blind Review Support**: Reviewers can evaluate cases without visual bias from automated scores, with on-demand unmasking.
5. **Tripartite Agreement Engine**: Deterministic classification of Model vs. Human, Rule vs. Human, and Model vs. Rule into 6 canonical states, never treating disagreement as an error.
6. **Append-Only Auditability**: Historical modifications produce distinct versioned review records with audit provenance and previous-decision links.
7. **Strict Provenance Integrity**: Synthetic incidents remain synthetic (`HUMAN_APPROVED_SYNTHETIC`), never elevated to real-world operational data.

---

## 2. Core Data Model & Version Locking

### 2.1 Authoritative Review Entity: `IncidentReview`

The `IncidentReview` model represents an authoritative, individual HSE domain adjudication. It is an append-only, immutable record with version locking.

| Field Name | Type | Description |
| :--- | :--- | :--- |
| `id` | `UUIDField` | Unique primary key. |
| `incident` | `ForeignKey(Incident)` | Link to target incident (`related_name="reviews"`). |
| `reviewer` | `ForeignKey(User)` | Authenticated HSE expert who authored the evaluation. |
| `decision` | `CharField(30)` | Canonical decision: `PSIF`, `NOT_PSIF`, or `INSUFFICIENT_INFORMATION`. |
| `rationale` | `TextField` | Substantive domain justification ($\ge 10$ characters). |
| `evidence_notes` | `TextField` | Field notes, discrepancy explanations, or attachment citations. |
| `structured_evidence` | `JSONField` | Structured anchors (hazard, exposure, control condition, IOGP rule). |
| `rubric_version` | `CharField(20)` | Evaluated HSE rubric version (default `"1.0"`). |
| `rubric_answers` | `JSONField` | Criteria answers across Hazard, Exposure, Control, Consequence, Sufficiency. |
| `was_blinded` | `BooleanField` | `True` if adjudication was performed without viewing ML scores. |
| `model_version` | `CharField(50)` | Locked active ML model version (e.g. `psif_rf_v1.0`). |
| `knowledge_base_version` | `CharField(50)` | Locked knowledge base version (`psif_kb_v1.0`). |
| `reasoning_ruleset_version`| `CharField(50)` | Locked reasoning ruleset version (`psif_ruleset_v1.0`). |
| `action_library_version` | `CharField(50)` | Locked action library version (`action_library_v1`). |
| `previous_decision` | `CharField(30)` | Decision from previous review record if this is an amendment. |
| `review_provenance` | `CharField(50)` | Provenance tag: `HUMAN_EXPERT`, `SYNTHETIC_SIMULATED`, or `HISTORICAL_AUDIT`. |
| `agreement_state` | `CharField(50)` | Tripartite alignment state (e.g., `MODEL_RULE_HUMAN_TRIPLE_AGREEMENT`). |
| `created_at` | `DateTimeField` | Immutable creation timestamp (`auto_now_add=True`). |
| `updated_at` | `DateTimeField` | Record update timestamp. |

### 2.2 Incident Adjudication State Fields

On `Incident`, adjudication status is reflected in consensus fields without altering predictive inputs:

- `adjudication_status`: `UNREVIEWED`, `UNDER_REVIEW`, or `ADJUDICATED`.
- `adjudicated_human_decision`: `PSIF`, `NOT_PSIF`, or `INSUFFICIENT_INFORMATION`.
- `adjudicated_by`: User reference to final adjudicator.
- `adjudicated_at`: Official timestamp of final decision.
- `adjudication_rationale`: Final consensus rationale.
- `psif_label_source`: Provenance category (`HUMAN_APPROVED_SYNTHETIC` or `REAL_HUMAN`).
- `effective_training_label`: Property resolving supervised training target (`True`, `False`, or `None` for insufficient).

---

## 3. Reviewer Workflow & User Experience

The Human Review Workbench is organized into two primary user experiences:
1. **The Review & Adjudication Queue** (`/predictions/review/`)
2. **The Review Case Page** (`/incidents/<uuid:pk>/adjudicate/`)

### 3.1 Review Case Page Architecture (Section 14 Hierarchy)

```
┌────────────────────────────────────────────────────────┐
│                   1. CASE HEADER                       │
│ Incident ID, Date, Site, Status, Official Narrative   │
├────────────────────────────────────────────────────────┤
│          2. TRIPARTITE SEPARATION GRID                 │
│ ┌───────────────┐ ┌───────────────┐ ┌────────────────┐ │
│ │ MODEL ASSESS  │ │ RULE ASSESS   │ │ HUMAN ADJUDIC  │ │
│ │ Score / SHAP  │ │ EEI / IOGP    │ │ Decision / Rat │ │
│ └───────────────┘ └───────────────┘ └────────────────┘ │
├────────────────────────────────────────────────────────┤
│          3. STRUCTURED EVIDENCE MATRIX                 │
│ Hazard, Exposure, Barrier Integrity, Severity, DQ      │
├────────────────────────────────────────────────────────┤
│          4. 7-NODE REASONING TRACE                     │
│ Transparent logical progression against psif_ruleset   │
├────────────────────────────────────────────────────────┤
│          5. GROUNDED CORRECTIVE ACTIONS                │
│ Pre-computed engineering, procedural, and stop-work    │
├────────────────────────────────────────────────────────┤
│          6. AUTHORITATIVE ADJUDICATION FORM            │
│ 3-State Radio [PSIF | NOT_PSIF | INSUFFICIENT]         │
│ Mandatory Rationale Textarea (>= 10 chars)             │
│ Optional Structured Anchors (Hazard, Exposure, Barrier)│
│ Reviewer Evidence Notes (Field citations/Disagreements)│
│ Submit Button (with Model Locking)                     │
├────────────────────────────────────────────────────────┤
│          7. AUDIT TRAIL & VERSION HISTORY              │
│ Complete timeline of all previous reviews & amendments │
└────────────────────────────────────────────────────────┘
```

### 3.2 Blind / Independent Review Flow (Section 7)

To eliminate confirmation bias where reviewers rubber-stamp automated model recommendations:
1. **Default Blind Mode**: When opening an unreviewed case, Blind Review Mode is active.
2. **Visual Masking**: The statistical model assessment panel displays a masked container explaining that automated scores are hidden to ensure unbiased domain evaluation.
3. **Manual Reveal Option**: The reviewer can click *"Reveal Model Assessment"* if they require access before submitting.
4. **Submit & Reveal**: Upon submitting an adjudication with `was_blinded=True`, the server saves `was_blinded=True` in the audit record and returns the unblinded model score, immediately displaying the tripartite agreement calculation.

---

## 4. Tripartite Reconciliation Engine (Section 8)

Review reconciliation calculates deterministic alignment across:
- **Statistical Model** (`prediction.psif_predicted`, `prediction.psif_probability`)
- **Rule-Grounded Engine** (`reasoning.decision`, `reasoning.state`)
- **Human Adjudication** (`review.decision`)

### Canonical Agreement States

| State | Definition | Operational Implication |
| :--- | :--- | :--- |
| `MODEL_RULE_HUMAN_TRIPLE_AGREEMENT` | Model, Rule, and Human all agree (e.g. all PSIF or all NOT PSIF). | High-confidence safety consensus. Standard corrective actions proceed. |
| `HUMAN_OVERRIDES_MODEL` | Human agrees with Rule, but overrides statistical ML model. | ML false positive/negative. Audit reason recorded; candidate for future training retraining set. |
| `HUMAN_OVERRIDES_RULE` | Human overrides deterministic rule assessment. | Contextual field exception or unmodeled barrier condition noted in evidence notes. |
| `HUMAN_INSUFFICIENT_INFORMATION` | Reviewer determines facts are inadequate to confirm or refute precursor. | Triggers field information request. Distinct from automated DQ or sparse text warnings. |
| `THREE_WAY_DISAGREEMENT` | Model, Rule, and Human all diverge. | Complex ambiguous incident. Requires peer review / multi-expert adjudication. |
| `AGREEMENT` | General agreement between human and available single automated source. | Solid consensus. |

Disagreement is explicitly **not treated as an error**. In high-hazard engineering, disagreement represents an invaluable organizational learning signal.

---

## 5. Review Queue & Deterministic Sorting (Section 12 & 13)

The review queue (`ReviewQueueView`) provides deterministic prioritization without fabricating arbitrary risk scores.

### 5.1 Structured Domain Filters

- **Review State**: `pending` (unadjudicated), `reviewed` (adjudicated), or `all`.
- **Decision**: `PSIF`, `NOT_PSIF`, `INSUFFICIENT_INFORMATION`, `unreviewed`.
- **Agreement State**: `MODEL_RULE_HUMAN_TRIPLE_AGREEMENT`, `HUMAN_OVERRIDES_MODEL`, `HUMAN_OVERRIDES_RULE`, `HUMAN_INSUFFICIENT_INFORMATION`, `THREE_WAY_DISAGREEMENT`.
- **Evidence Strength**: `Strong`, `Moderate`, `Weak`.
- **Data Quality Warnings**: Flagged by automated screening (`WARNING`, `CRITICAL`).
- **Sparse Input**: Narratives $< 10$ words.
- **IOGP Life-Saving Rules**: Matched rule category.
- **Site / Department**: Free-text filtering across department and location.
- **Date Range**: `date_from` and `date_to`.
- **Activity**: Free-text search across job task and narrative.

### 5.2 Deterministic Sorting Semantics

1. **`priority` (Default)**: Derived strictly from structured domain criteria:
   - *Tier 1*: High-priority Disagreement / Overrides (`THREE_WAY_DISAGREEMENT`, `HUMAN_OVERRIDES_MODEL`, `HUMAN_OVERRIDES_RULE`).
   - *Tier 2*: Weak Evidence PSIF Candidates (high ML score + weak evidence).
   - *Tier 3*: Pending unreviewed PSIF candidates.
   - *Tier 4*: Other pending unreviewed incidents.
   - *Tier 5*: Already adjudicated records.
2. **`newest`**: Sorted by `-incident_date`, `-created_at`.
3. **`weak_evidence`**: Sorted by `evidence_strength` ascending (`Weak` $\to$ `Moderate` $\to$ `Strong`).
4. **`disagreement`**: Incidents with active disagreement states first.
5. **`unreviewed`**: Pending cases first, sorted by model score descending.

---

## 6. Review Analytics & Inter-Rater Reliability (Section 20 & 21)

### 6.1 Explicit Mathematical Denominators

Every analytical percentage in Foresight must display its explicit mathematical denominator to prevent statistical distortion:
- **Review Coverage**: $\frac{\text{Reviewed Incidents}}{\text{Total Incidents}} \times 100\%$ (e.g. `24 / 100 (24.0%)`).
- **PSIF Adjudication Rate**: $\frac{\text{PSIF Decisions}}{\text{Total Reviews}} \times 100\%$ (e.g. `12 / 24 (50.0%)`).
- **Model vs Human Agreement**: $\frac{\text{Agreed Cases}}{\text{Cases with both Model \& Human}} \times 100\%$ (e.g. `18 / 20 (90.0%)`).

### 6.2 Inter-Rater Reliability Safety Guard

When calculating Cohen's Kappa ($\kappa$) or inter-rater agreement:
- **Rule**: If distinct genuine human reviewers $< 2$, the system strictly displays:
  > *"Insufficient reviewer coverage for inter-rater analysis."*
- **Constraint**: Synthetic reviewer simulation records (`is_synthetic=True`) are **never** counted as genuine human reviewers.
- **Dual-Review Cohort**: When $\ge 2$ genuine human reviewers review overlapping cases, pairwise agreement and Cohen's Kappa are computed across the intersection.

---

## 7. Security, Permissions & Submission Safety (Section 15)

1. **Authentication**: All review submissions require active Django session or token authentication. Unauthenticated requests return HTTP 401/403.
2. **Role-Based Access Control (RBAC)**:
   - `Viewer` role (`user.is_viewer = True`): Read-only access. Attempted review submissions return HTTP 403 Forbidden.
   - `Safety Officer` & `Analyst` (`user.can_predict = True`): Authorized to submit adjudications.
   - `Admin`: Full adjudication and audit privileges.
3. **Identity Verification**: Reviewer identity is bound strictly to `request.user` on the server. Frontend-supplied user IDs, roles, or incident ownership claims are discarded.
4. **Idempotency & Duplicate Submission Protection**: Submissions with identical decision and rationale within 3 seconds of a previous submission are detected as duplicate retries and handled idempotently without corrupting the audit log.

---

## 8. Provenance & Future Training Data Contract (Section 17 & 19)

### 8.1 Provenance Hierarchy

| Category | Description | Treatment |
| :--- | :--- | :--- |
| `SYNTHETIC` | Unreviewed benchmark or simulated evaluation cases. | Retained in benchmark pool. |
| `HUMAN_APPROVED_SYNTHETIC` | Synthetic incidents reviewed and approved by a genuine human HSE expert. | Elevated to human-approved benchmark set. **Never called OIL validated.** |
| `REAL_EXTERNAL` | Real-world external incidents (e.g. OSHA records). | Preserved as external data. |
| `REAL_HUMAN` | Genuine enterprise operational incidents. | Authentic real-world data. |

### 8.2 Future Training Data Contract

To prevent training feedback leakage:
1. **No Silent Online Feedback**: Human reviews **never** immediately update inference weights or pipeline configurations.
2. **Explicit Candidate Export**: Adjudicated cases with substantive rationales become candidates for the versioned training pool via explicit dataset promotion (`effective_training_label`).
3. **Insufficient Information Exclusion**: Incidents adjudicated as `INSUFFICIENT_INFORMATION` resolve `effective_training_label = None`. They are **strictly excluded** from binary supervised training targets and are never converted to negative labels.

---

## 9. Limitations & Non-Goals

1. **No Automated Overwrite**: Machine learning models and rule engines will never automatically accept human decisions as ground truth without scheduled offline evaluation.
2. **No Narrative Alteration**: Reviewer notes and structured evidence are preserved as separate reviewer annotations; the original field narrative remains permanently unmutated.
3. **No Fabricated Statistics**: Inter-rater reliability, agreement metrics, and coverage percentages are never simulated or extrapolated when underlying data is absent.
