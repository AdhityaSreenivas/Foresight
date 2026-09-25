# Why PSIF / Why NOT PSIF / Evidence-Break Workbench Specification

## 1. Executive Summary & Objective

The **Why PSIF / Why NOT PSIF / Evidence-Break Workbench** is Foresight's authoritative explainability and forensic evidence-analysis experience for Potential Serious Injury and Fatality (PSIF) determinations.

Designed specifically as an **HSE Investigation and Adjudication Workbench** rather than a generic machine-learning dashboard, the interface enables safety officers, field investigators, and HSE directors to systematically understand:
1. **WHAT DID FORESIGHT FIND?** (Official safety classification, hazard family, critical control condition, worker exposure envelope)
2. **WHY PSIF?** (Affirmative open precursor pathway where uncontained high energy intersected an exposed worker through a failed, absent, or unverified barrier)
3. **WHY NOT PSIF?** (High-energy hazard was arrested or controlled by an effective barrier [Capacity], or the event lacked physical high-energy density)
4. **WHAT EVIDENCE SUPPORTS THAT?** (Direct narrative excerpts, verified structured safety fields, and rule provenance)
5. **WHAT EVIDENCE IS MISSING?** (Critical gaps in isolation verification, standoff distance, or control state)
6. **WHAT RULE/CONTROL MATTERS?** (Authoritative safety classification rules and physical barrier hierarchy)
7. **WHAT WOULD CHANGE THE ASSESSMENT?** (Actionable evidentiary conditions that would alter or finalize the determination)
8. **WHAT SHOULD HSE CONSIDER DOING NEXT?** (Evidence-grounded operational next steps from Foresight's Action Engine)

---

## 2. Architectural Boundary & Anti-Duplication Rule

```
[ Incident Record & Free Text ] 
              │
              ▼
[ Deterministic Reasoning Engine & Action Engine ]  (Backend)
              │
              ▼
   GET /api/incidents/<uuid>/reasoning/            (Authoritative JSON Contract)
              │
              ▼
[ Evidence-Break Workbench Presentation Layer ]   (Templates & DOM View)
```

### Critical Architectural Invariants:
1. **Zero Logic Duplication**: The frontend is purely a presentation and visualization layer. It **does NOT** implement a second PSIF classifier or heuristic evaluator in JavaScript.
2. **Authoritative Backend Contract**: Reasoning is never reconstructed from keywords, raw strings, model scores, or IOGP tags in the browser. All states, conclusions, and actions are rendered directly from `GET /api/incidents/<uuid>/reasoning/` and server-rendered context.
3. **Official Decision Vocabulary**:
   - `PSIF`: Credible open SIF precursor pathway established.
   - `NOT PSIF`: Pathway controlled or low energy.
   - `INSUFFICIENT INFORMATION`: Critical facts unverified or contradictory.
   - Prohibited as substitutes: *HIGH RISK*, *CRITICAL*, *CONFIDENCE*.

---

## 3. Page Information Architecture

The workbench layout enforces an intentional visual hierarchy tailored for safety analysis:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. HEADER & INCIDENT METADATA                                              │
│    ID, Date, Site, Department, Activity, Decision, Score, Strength, Review │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2. HIGH-PRIORITY REVIEW CALLOUT (Conditional)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3. EXECUTIVE DECISION SUMMARY BANNER                                        │
│    Official Decision Box + Deterministic Executive Narrative                │
├─────────────────────────────────────────────────────────────────────────────┤
│ 4. SIF PRECURSOR EVIDENCE CHAIN (Interactive 7-Node Flow)                   │
│    Hazard → Worker Exposure → Critical Control → Control State             │
│    → Barrier Pathway → Consequence → Authoritative Decision                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ 5. CONFLICTING EVIDENCE CALLOUT (Rendered when Material Contradiction Exists)│
│    Statement A (Barrier) vs Statement B (Observation) + Resolution Path     │
├─────────────────────────────────────────────────────────────────────────────┤
│ 6. CONTEXTUAL DEEP DIVE (2-Column Grid)                                     │
│    Left: Why PSIF / Why NOT PSIF        Right: Evidence Gaps / What Would   │
│          Pathway Analysis                      Change This Assessment       │
├─────────────────────────────────────────────────────────────────────────────┤
│ 7. EVIDENCE STRENGTH MATRIX (Interactive 6-Dimension Accordion)             │
│    Hazard | Exposure | Control | State | Pathway | Sufficiency              │
│    With Expandable "Why This Evidence Matters" Drawers                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ 8. SOURCE TRACEABILITY & EXCERPTS (2-Column Grid)                           │
│    Left: Extracted Narrative Quotes     Right: Structured DB Field Mappings │
├─────────────────────────────────────────────────────────────────────────────┤
│ 9. RULES & IOGP SEPARATION (2-Column Grid)                                  │
│    Left: Safety Standard Rules          Right: IOGP Life-Saving Rules       │
│          psif_ruleset_v1.0                     Independence Disclaimer      │
├─────────────────────────────────────────────────────────────────────────────┤
│ 10. GROUNDED ACTIONS & NEXT STEPS (Action Engine v1 Cards)                  │
│     Immediate | Restoration | Verification | Corrective | Preventive        │
├─────────────────────────────────────────────────────────────────────────────┤
│ 11. MODEL VS RULE RECONCILIATION & SHAP ANALYSIS                            │
│     Statistical ML Model vs Rule Engine + Positive / Negative Contributors │
├─────────────────────────────────────────────────────────────────────────────┤
│ 12. METHODOLOGY & PROVENANCE DISCLOSURES (Centralized Notices)              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Component-by-Component Specification

### 4.1 Header & Metadata Strip
- **Path**: Top of page (`.wb-header-card`).
- **Data Points**:
  - `Incident ID`: Full UUID formatted in monospace.
  - `Date Occurred`: Formatted as `YYYY-MM-DD`.
  - `Facility / Site`: Physical operational location.
  - `Department`: Operational unit.
  - `Activity / Task`: Work task or energy source being manipulated.
  - `Review Status`: `ADJUDICATED` (green), `UNDER_REVIEW` (amber), or `UNREVIEWED` (slate).
  - `Knowledge Base Version`: e.g. `psif_kb_v1.0`.
  - `Action Library Version`: e.g. `action_library_v1`.

### 4.2 Executive Decision Summary Banner
- **Visual Presentation**: High-contrast decision box with dynamic background states:
  - `state-psif`: Red border, bold PSIF badge.
  - `state-not-psif`: Green border, bold NOT PSIF badge.
  - `state-insufficient`: Amber border, bold INSUFFICIENT INFORMATION badge.
  - `state-conflict`: Dark-red border, bold CONFLICTING EVIDENCE badge.
- **Authoritative Executive Statements**:
  - *PSIF*: *"An open high-energy SIF pathway is supported by the available evidence."*
  - *Controlled High Energy*: *"The available evidence indicates that the high-energy pathway was controlled or interrupted."*
  - *Low Energy*: *"The available evidence indicates that the physical mechanism lacked the high energy required to cause a fatal or permanent disabling outcome."*
  - *Conflicting*: *"Conflicting evidence prevents a reliable automated determination."*
  - *Insufficient*: *"Available information is insufficient to establish or refute the PSIF pathway."*
- **Metrics Strip**:
  - `PSIF Model Score`: Continuous ML score formatted to 4 decimal places.
  - `Evidence Strength`: `HIGH`, `MODERATE`, or `LOW`.
  - `Hazard Family`: Normalized taxonomy name.
  - `Critical Barrier`: Primary physical barrier identified.

### 4.3 Core SIF Precursor Reasoning Chain
- **Concept**: A 7-step sequential audit chain representing the physical progression of the potential event:
  1. `Hazard Source`: Presence of fatal-capable high energy.
  2. `Worker Exposure`: Personnel within release envelope or line of fire.
  3. `Critical Control`: Engineered barrier or physical defense.
  4. `Control State`: `EFFECTIVE`, `FAILED`, `BYPASSED`, `ABSENT`, or `NOT_VERIFIED`.
  5. `Barrier / Pathway`: Whether energy release pathway was `INTERRUPTED` or `OPEN`.
  6. `Consequence`: Credible physical mechanism for fatal / life-altering trauma.
  7. `Decision`: Final reconciled classification.
- **Interactive Capabilities**:
  - Keyboard and click expandable: Clicking a node expands the full finding text.
  - Status badges: Color-coded with explicit accessible status text (`SUPPORTED`, `INTERRUPTED`, `FAILED / OPEN`, `MISSING / UNCERTAIN`).
  - Mandatory disclaimer: *"This is an evidence representation, not a causal claim."*

### 4.4 Why PSIF Analysis (When Decision = PSIF)
- Structured 4-stage breakdown:
  1. *High-Energy Hazard*: Energy type and verified operational magnitude.
  2. *Worker Exposure Envelope*: Position relative to release trajectory.
  3. *Critical Direct Control & State*: Barrier compromised, failed, or omitted.
  4. *Pathway Integrity & Mechanism*: Supported physical mechanism.
- Concluding Rationale: Explicitly explains **why the pathway remained open** (e.g. unverified isolation before line break).

### 4.5 Why NOT PSIF Analysis (When Decision = NOT PSIF)
- Differentiates between two fundamentally distinct safety realities:
  - **Controlled High Energy (Capacity)**: High energy present, but physical direct barrier held (e.g. exclusion zone barricade, trench shoring), keeping workers completely protected. Pathway marked `INTERRUPTED`.
  - **Low Energy**: Hazard lacked the physical capacity to cause death or permanent disability (e.g. minor tripping hazard, ergonomic strain).
- Prohibits superficial explanations like *"Model score was low"*.

### 4.6 Insufficient Information Experience
- Activated whenever evidence is sparse or critical barrier/exposure facts are unrecorded.
- Features:
  - **What is Known**: Verified operational facts.
  - **What is Unknown**: Critical missing dimensions.
  - **Why it Matters**: Safety impact of the unknown (e.g. separates controlled high energy from open release).
  - **Evidence Needed to Close the Case**: Specific investigative questions and verification items needed from the field.

### 4.7 Conflicting Evidence Callout
- Triggers when material contradictions exist in the incident narrative (e.g. permit claims verified isolation, but narrative reports residual pressure escaped during flange loosen).
- Never selects one statement silently.
- Renders:
  - **Statement A**: Reported control / barrier measure.
  - **Statement B**: Observed release / worker strike.
  - **Why the conflict matters**: Explains how the contradiction blocks automated determination.
  - **What needs to be verified**: Investigation checklist (permit logs, witness statements).
  - **Human Review Recommendation**: Mandatory investigator adjudication banner.

### 4.8 Evidence Strength Matrix & "Why This Evidence Matters"
- Evaluates 6 core dimensions:
  1. *High-energy hazard*
  2. *Worker exposure*
  3. *Critical control*
  4. *Control state*
  5. *SIF pathway*
  6. *Evidence sufficiency*
- **Expandable Drawer**:
  - *What the Evidence Says*: Textual or structured finding.
  - *Why it Matters to PSIF Pathway*: Safety engineering significance.
  - *Related Rule / Source*: Rule ID and taxonomy citation.

### 4.9 Source Traceability & Excerpts
- **Left Column**: Verbatim narrative excerpts extracted from the incident text supporting each reasoning dimension.
- **Right Column**: Direct structured database field mappings (Energy Type, High Energy Present, Worker Exposed, Control Condition, Severity Potential) showing reported values vs engine interpretation.

### 4.10 Rules Evaluated & IOGP Life-Saving Rules Separation
- **psif_ruleset_v1.0**: Lists deterministic safety engineering rules evaluated.
- **IOGP Life-Saving Rules (Report 459)**:
  - Displays applicable IOGP rule (e.g. *Energy Isolation*, *Bypass Safety Controls*, *Line of Fire*).
  - Explicit **Independence Disclaimer**:
    > *"Rule match indicates operational activity type and does not by itself establish an IOGP rule violation or PSIF status. Likewise, an IOGP rule violation does not automatically imply a credible SIF pathway without direct worker exposure."*
  - Prohibits displaying pseudoscientific "100% confidence" tags.

### 4.11 Grounded Actions & Next Steps (Action Engine v1)
- Formatted as responsive cards categorized by action type:
  - `IMMEDIATE_ACTION`: Stop work, isolate energy, evacuate zone.
  - `CONTROL_RESTORATION`: Re-establish physical barrier, repair valve.
  - `VERIFICATION_ACTION`: Zero energy test, physical audit.
  - `CORRECTIVE_ACTION`: Engineering redesign, procedure revision.
  - `PREVENTIVE_ACTION`: Maintenance schedule update, training.
  - `ESCALATION_ACTION`: Senior leadership notification, regulatory reporting.
  - `POSITIVE_LEARNING`: Capacity verification and commendation for effective controls.
- Each action displays: Urgency, Title, Description, Reason, Triggering Evidence, Control Addressed, Rule Citation, and Verification Steps Checklist.
- Mandatory Action Guidance:
  > *"Suggested next steps — verify against applicable site procedures and HSE requirements."*

### 4.12 Model vs Rule Reconciliation & SHAP Contributors
- **Side-by-Side Comparison**:
  - *Column 1*: Statistical ML Model prediction, continuous PSIF Model Score, threshold.
  - *Column 2*: Rule-Grounded Domain Engine decision, internal state, agreement status.
  - *Agreement States*: `MODEL_AND_RULE_AGREE`, `MODEL_PSIF_RULE_NON_PSIF`, `RULE_PSIF_MODEL_NON_PSIF`, `INSUFFICIENT_EVIDENCE`.
- **SHAP Feature Analysis**:
  - Divided cleanly into **Positive Contributors** (pushing toward PSIF) and **Negative Contributors** (pulling toward NOT PSIF).
  - Suppressed features: Noise threshold (|contribution| &le; 0.001) filtered out and placed in an expandable summary.
  - Mandatory SHAP Notice: *"Model contribution — not causality."*

### 4.13 High-Priority Review CTA Banner
- Prominently shown whenever:
  - `high_priority_review = True` (conflicting evidence, model/rule disagreement, or critical missing fields).
- Displays direct navigation button to the Human Review and Adjudication workflow (`/incidents/<id>/#review-section`).

---

## 5. Responsive Design & Accessibility

### 5.1 Breakpoint Strategy
- **Desktop (> 1024px)**: 2-column balanced layouts, horizontal 7-node chain with connected arrow indicators, side-by-side model vs rule reconciliation.
- **Tablet (768px - 1024px)**: Stacked 1-column layouts for narrative excerpts and rules; 2-column action cards.
- **Mobile (< 768px)**: Strict 1-column layout, touch-friendly expandable accordion rows (minimum 44px tap targets), horizontal overflow prevention, wrapped metadata strips.

### 5.2 Accessibility Standards (WCAG 2.1 AA)
- Semantic HTML tags: `<header>`, `<main>`, `<article>`, `<section>`, `<footer>`, `<table>`.
- Status indicators do not rely solely on color: every state includes explicit textual labeling (`SUPPORTED`, `FAILED`, `INTERRUPTED`, `MISSING`).
- Accordions and chain nodes include `aria-expanded`, `tabindex="0"`, and keyboard handlers for `Enter` and `Space`.

---

## 6. Verification & Automated Test Coverage

The workbench implementation is verified by a 16-test comprehensive test suite in `tests/test_evidence_break_workbench.py`:

| Test Name | Verification Focus | Result |
|---|---|---|
| `test_obvious_not_psif_incident` | Verifies low score, broken chain links, and NOT PSIF classification. | **PASSED** |
| `test_sparse_narrative_incident` | Verifies sparse report detection (< 10 words) and evidence-limited state. | **PASSED** |
| `test_missing_exposure_evidence` | Verifies hazard present without worker exposure creates broken link. | **PASSED** |
| `test_hazard_without_consequence` | Verifies low-energy hazard does not trigger fatal SIF pathway. | **PASSED** |
| `test_narrative_and_structured_disagreement_traceability` | Verifies cross-field traceability and reconciliation. | **PASSED** |
| `test_unknown_versus_not_psif_distinction` | Verifies genuine unknown facts are never classified as implicit NOT PSIF. | **PASSED** |
| `test_human_insufficient_information_governance` | Verifies high-priority review trigger on insufficient information. | **PASSED** |
| `test_api_unauthenticated_returns_401` | Verifies RBAC security on reasoning API. | **PASSED** |
| `test_api_nonexistent_incident_returns_404` | Verifies missing incident 404 response. | **PASSED** |
| `test_api_returns_complete_evidence_break_payload` | Verifies full schema delivery from API. | **PASSED** |
| `test_ui_evidence_break_view_renders_successfully` | Verifies UI template rendering for authenticated analysts. | **PASSED** |
| `test_ui_detail_page_includes_evidence_break_widget` | Verifies seamless linkage from Incident Detail page. | **PASSED** |
| `test_ui_psif_case_renders_why_psif_and_open_pathway` | Verifies affirmative PSIF UI, open pathway, actions, and source trace. | **PASSED** |
| `test_ui_controlled_high_energy_case_renders_interrupted_pathway` | Verifies capacity case, interrupted pathway, and matrix rendering. | **PASSED** |
| `test_ui_insufficient_information_renders_checklist` | Verifies dedicated evidence gap checklist and review banner. | **PASSED** |
| `test_ui_conflicting_evidence_renders_explicit_conflict_card` | Verifies Statement A vs Statement B conflict card rendering. | **PASSED** |

---

## 7. Conclusion & Compliance

The Evidence-Break Workbench satisfies all requirements of **TASK 7**:
- **Authoritative & Deterministic**: Consumes `GET /api/incidents/<uuid>/reasoning/` without client-side recomputation.
- **Comprehensive SIF Forensic Explainability**: Delivers the complete 11-stage reasoning hierarchy.
- **HSE-Centric & Actionable**: Provides grounded actions, missing evidence questions, and review governance.
