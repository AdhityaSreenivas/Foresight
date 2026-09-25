# Foresight PSIF Decision Policy Specification

**Document Identifier**: `docs/PSIF_DECISION_POLICY.md`  
**System Evaluated**: Foresight PSIF Reasoning Engine & Decision Reconciliation Layer  
**Engine Version**: `psif_ruleset_v1.0`  
**Knowledge Base Version**: `psif_kb_v1.0`  
**Effective Date**: September 2026  
**Status**: **FROZEN & AUTHORITATIVE**  

---

## 1. Executive Summary & Epistemic Authority

This document defines the deterministic policy governing incident classification, machine learning reconciliation, evidence strength assessment, and human escalation across the Foresight platform.

### Foundational Principle: The Knowledge Layer is the Authority
1. **Physics Over Correlation**: The physical reality of hazardous energy, worker positioning, and barrier integrity governs safety classification. Statistical correlations derived from language models or XGBoost classifiers are advisory and analytical, not regulatory authorities.
2. **Deterministic Sequence**: All incidents are evaluated through an unvarying 10-stage physical reasoning sequence.
3. **No Silent Overrides**: Disagreements between statistical models and deterministic physical rules are never silently averaged, suppressed, or overwritten. Every disagreement is explicitly labeled as `POTENTIAL_FALSE_NEGATIVE` or `POTENTIAL_FALSE_POSITIVE` and escalated for high-priority human review.
4. **Epistemic Modesty**: Incomplete, sparse, or materially contradictory reporting strictly produces `INSUFFICIENT_INFORMATION` rather than speculative binary classifications.

---

## 2. Canonical State Space

The platform enforces a strict separation between internal physical reasoning states and user-facing decisions. Individual frontend views or API consumers are **prohibited** from inventing custom state interpretations.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        CANONICAL REASONING STATE SPACE                                 │
├──────────────────────────┬──────────────────────────┬──────────────────────────────────┤
│ Internal Reasoning State │ User-Facing Decision     │ Physical Meaning                 │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ PSIF_PATHWAY_OPEN        │ PSIF                     │ High energy + worker exposed +   │
│                          │                          │ direct control compromised.      │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ HIGH_ENERGY_CONTROLLED   │ NOT_PSIF                 │ High energy present, but direct  │
│                          │                          │ barrier or safe positioning held │
│                          │                          │ (EEI SCL Capacity).              │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ LOW_ENERGY               │ NOT_PSIF                 │ Physical energy below credible   │
│                          │                          │ SIF threshold (minor hazard).    │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ INSUFFICIENT_INFORMATION │ INSUFFICIENT_INFORMATION │ Essential exposure, control, or  │
│                          │                          │ energy facts omitted.            │
├──────────────────────────┼──────────────────────────┼──────────────────────────────────┤
│ CONFLICTING_EVIDENCE     │ INSUFFICIENT_INFORMATION │ Narrative contains mutually      │
│                          │ (Flagged High Priority)  │ contradictory safety statements. │
└──────────────────────────┴──────────────────────────┴──────────────────────────────────┘
```

---

## 3. Ten-Stage Physical Decision Sequence

The reasoning engine processes every incident through the following sequential evaluation:

```
[A] High-Energy Hazard Established?
 │    NO ──► LOW_ENERGY ──► User: NOT_PSIF
 ▼ YES
[B] Credible Worker Exposure Established?
 │    NO / PROTECTED ──► HIGH_ENERGY_CONTROLLED ──► User: NOT_PSIF
 ▼ YES / CREDIBLE
[C] Relevant Direct/Critical Control Identified?
 │    UNKNOWN ──► INSUFFICIENT_INFORMATION
 ▼ IDENTIFIED
[D] Actual Control State Evaluated (12 States)?
 │    UNKNOWN ──► INSUFFICIENT_INFORMATION
 ▼ DETERMINED
[E] Did Control or Barrier Interrupt Pathway?
 │    YES (Effective / Restored Before) ──► HIGH_ENERGY_CONTROLLED ──► User: NOT_PSIF
 ▼ NO (Failed / Bypassed / Absent)
[F] Credible SIF Consequence Mechanism Established?
 │    NO / UNKNOWN ──► INSUFFICIENT_INFORMATION
 ▼ YES
[G] Available Evidence Sufficient (Evidence Contract Checked)?
 │    NO (Missing Key Facts) ──► INSUFFICIENT_INFORMATION
 ▼ YES
[H] Material Contradictions Detected?
 │    YES (Conflicting Claims) ──► CONFLICTING_EVIDENCE (High Priority Review)
 ▼ NO
[I] Internal Reasoning State: PSIF_PATHWAY_OPEN
 ▼
[J] User-Facing Decision: PSIF
```

---

## 4. Machine Learning & Rule Reconciliation Policy

The machine learning model outputs a continuous `psif_score` ($0.0 - 1.0$) and a thresholded prediction (`PSIF` or `NOT PSIF`). The rule engine evaluates physical evidence deterministically. The reconciliation policy resolves these inputs according to the matrix below:

| Rule Assessment | ML Prediction | Agreement State | Policy Final Decision | High Priority Review | Disagreement Classification |
|:---|:---|:---|:---|:---:|:---|
| **PSIF** | **PSIF** | `MODEL_AND_RULE_AGREE` | **PSIF** | No | None (Consensus) |
| **NOT_PSIF** | **NOT_PSIF** | `MODEL_AND_RULE_AGREE` | **NOT_PSIF** | No | None (Consensus) |
| **PSIF** | **NOT_PSIF** | `RULE_EVIDENCE_STRONGER_THAN_MODEL` | **PSIF** | **YES** | `POTENTIAL_FALSE_NEGATIVE` |
| **NOT_PSIF** | **PSIF** | `MODEL_STRONGER_THAN_RULE_EVIDENCE` | **NOT_PSIF** | **YES** | `POTENTIAL_FALSE_POSITIVE` |
| **INSUFFICIENT** | Any | `INSUFFICIENT_EVIDENCE` | **INSUFFICIENT_INFORMATION** | **YES** | None (Evidence Deficit) |
| Any | Any | `DATA_QUALITY_BLOCKED` | **INSUFFICIENT_INFORMATION** | **YES** | Critical DQ Failure |

### Disagreement Rationale Explanations

#### 1. Potential False Negative (`RULE_EVIDENCE_STRONGER_THAN_MODEL`)
- **Condition**: Deterministic rules identify a verified high-energy hazard, credible worker exposure, and an ineffective or bypassed direct barrier, but the ML score falls below threshold.
- **Root Cause**: Field reporting used neutral, passive, or procedural language (e.g. "coupling guard was removed during rotation check") lacking alarming vocabulary that statistical models rely upon.
- **Policy Stance**: **Safety-First Override for Action**. The policy decision is `PSIF`. The case is flagged for high-priority human review with the alert:  
  *"Rule-grounded evidence establishes an open SIF pathway (high energy with control failure and worker exposed), but statistical model score fell below threshold. Potential false negative."*

#### 2. Potential False Positive (`MODEL_STRONGER_THAN_RULE_EVIDENCE`)
- **Condition**: The ML model assigns a high score ($> \text{threshold}$), but deterministic rules confirm that direct controls held effectively or personnel were protected.
- **Root Cause**: The narrative contained dramatic high-energy keywords ("massive crane", "500-ton press", "catastrophic burst") which inflated statistical word embeddings, despite verified barricades or standoff distance.
- **Policy Stance**: **Capacity Acknowledged**. The policy decision is `NOT_PSIF`. The case is flagged for review to verify barrier integrity with the alert:  
  *"Direct controls held effectively (EEI SCL Capacity) or worker was protected; high-energy keywords alone do not constitute an open PSIF pathway."*

---

## 5. Evidence Strength Quantification

Evidence strength describes the degree of corroboration and completeness, **not** statistical probability:

- **`STRONG`**:
  - High-energy source explicitly documented with operating parameters ($\ge 10\text{ bar}$, $\ge 1.8\text{ m}$, $\ge 415\text{V}$, or specific equipment).
  - Worker position explicitly corroborated (inside line of fire or behind verified barrier).
  - Direct barrier condition verified by observation or test.
  - Zero material contradictions and zero critical missing evidence prompts.
- **`MODERATE`**:
  - Hazard and exposure established from narrative or structured fields.
  - Minor operational details missing but critical barrier state is clear.
- **`WEAK`**:
  - Significant information gaps ($\ge 2$ missing evidence contract items).
  - Sparse narrative ($< 10$ words) without corroborating structured fields.
- **`CONFLICTING`**:
  - Assigned when mutually contradictory statements exist in the text. Triggers `CONFLICTING_EVIDENCE`.

---

## 6. Anti-Inference Protection Policy

The platform enforces 13 declarative constraints preventing the engine from drawing unwarranted conclusions:

1. **Hazard $\ne$ Exposure**: Operating high-energy equipment within design specifications is normal industrial activity.
2. **IOGP Match $\ne$ Violation**: Citing a life-saving rule does not imply it was violated.
3. **IOGP Lapse $\ne$ PSIF**: Administrative procedural paperwork lapses do not constitute physical energy releases.
4. **Control Mention $\ne$ Effectiveness**: Merely referencing a barrier does not prove it functioned as rated.
5. **Control Mention $\ne$ Failure**: Mentioning a guardrail does not mean it failed.
6. **Corrective Action $\ne$ Event Evidence**: Post-incident action items are strictly quarantined from event reasoning.
7. **Planned Action $\ne$ Completed Barrier**: Commitments to install guards tomorrow do not protect workers today.
8. **PPE Availability $\ne$ Use**: Having safety gear in a locker does not mean it was worn.
9. **PPE Use $\ne$ Direct Control**: Ordinary PPE is the lowest hierarchy level and cannot eliminate nip points or pressure sprays.
10. **LOTO Mention $\ne$ Zero Energy**: Lockout without verified test-before-touch is unverified.
11. **Near Miss $\ne$ PSIF**: Low-energy near misses (e.g. office trip) are not SIF precursors.
12. **High Energy Equipment $\ne$ PSIF**: Operating equipment without release is safe work.
13. **Dramatic Adjectives $\ne$ PSIF**: Words like "catastrophic" or "dangerous" without physical exposure do not trigger PSIF.

---

## 7. Action Grounding & Decoupling Policy

Action recommendations are derived from the versioned `ACTION_LIBRARY` based upon the reconciled reasoning state:
1. **Actions Are Strictly Downstream**: Action selection cannot influence the classification of the incident.
2. **Hierarchy-of-Controls Enforcement**: When `PSIF_PATHWAY_OPEN` occurs, `IMMEDIATE_ACTION` (Stop Work) and `CONTROL_RESTORATION` (Engineered Barrier) are prioritized over administrative instructions.
3. **Positive Control Learning**: When `HIGH_ENERGY_CONTROLLED` occurs, the engine generates `POSITIVE_LEARNING_ACTION` recognizing successful barrier capacity.
4. **Investigation Actions**: When `INSUFFICIENT_INFORMATION` or `CONFLICTING_EVIDENCE` occurs, the engine generates `VERIFICATION_ACTION` and evidence-gathering checklists.

---

## 8. Frozen Contract Sign-Off

The decision policy codified in this document is verified by automated regression suites and is hereby **FROZEN**. Downstream user-facing feature development (dashboards, workbench views, corrective action workflows) must consume this API contract without altering decision semantics.
