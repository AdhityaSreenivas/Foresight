# Foresight Action & Next-Step Engine Specification

**Document Version:** 1.0-FROZEN  
**Status:** VALIDATED & OPERATIONAL  
**Module:** `apps.incidents.knowledge.action_mappings` & `apps.incidents.services.action_library`  
**Reasoning Layer Consumer:** `apps.incidents.services.psif_reasoning.select_grounded_actions`  
**Library Version:** `action_library_v1`  
**Date:** 2026-09-10  
**Test Suite:** `tests/test_action_engine.py` (42 / 42 passing)  

---

## 1. Primary Objective & Architectural Pipeline

The Foresight Action & Next-Step Engine is an evidence-grounded, deterministic safety next-step recommendation system. It answers the core operational question:

> *"Given what Foresight has actually established about this incident, what should an HSE analyst consider doing next?"*

It deliberately does **NOT** answer:
> *"What generic safety advice sounds appropriate for this incident?"*

### Operational Pipeline
The Action Engine never performs free-form generative prompting or ungrounded hazard classification. It operates strictly as a downstream consumer of the canonical PSIF Reasoning Engine:

```
┌────────────────────────────────────────────────────────┐
│                   INCIDENT RECORD                      │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│            STRUCTURED EVIDENCE SYNTHESIS               │
│  (Hazard, Energy, Exposure, Control State, Pathway)    │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│                PSIF REASONING STATE                    │
│   (PSIF_PATHWAY_OPEN | HIGH_ENERGY_CONTROLLED | ...)   │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│               CONTROL CONDITION EVALUATION             │
│  (EFFECTIVE | FAILED | BYPASSED | ABSENT | UNVERIFIED) │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│             APPLICABLE REGULATORY/IOGP RULE            │
│  (IOGP 459 | OSHA 1910/1926 | OISD 192 | EEI SCL)      │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│              DETERMINISTIC ACTION MAPPING              │
│       (15 Hazard Families × 7 Action Categories)       │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│              CONTEXTUALIZED, AUDITABLE ACTION          │
│       (Deduplicated, Prioritized, Fully Traceable)     │
└────────────────────────────────────────────────────────┘
```

---

## 2. Authoritative Source of Truth & Quarantine Isolation

### Strictly Downstream Consumer
The Action Engine:
1. **MUST NOT** independently infer PSIF from the raw narrative.
2. **MUST NOT** introduce a separate hazard classifier.
3. **MUST NOT** reinterpret evidence that was already resolved by the reasoning layer.
4. **MUST NOT** feed its action recommendations back into the PSIF model or reasoning engine (Anti-Inference & Leakage Quarantine).

### Leakage Quarantine Guarantee
As proven in `TestAntiInferenceAndQuarantineLeakage`, modifying the incident's corrective action text or generated recommendations has zero impact on the initial PSIF decision, internal reasoning state, hazard identification, or worker exposure classification.

---

## 3. Seven Canonical Action Categories

Actions are never collapsed into generic "corrective actions." Foresight recognizes 7 distinct action types based on operational intent and the hierarchy of controls:

| Category | Identifier | Operational Purpose | Default Urgency |
|---|---|---|---|
| **A. Immediate Action** | `IMMEDIATE_ACTION` | Halt active exposure; remove personnel from hazardous release path; trip emergency shutdowns (ESD). | `CRITICAL` |
| **B. Control Restoration** | `CONTROL_RESTORATION` | Re-establish, repair, or replace the direct engineered barrier (e.g. shoring box, whip checks, lanyards, blind flanges). | `HIGH` |
| **C. Verification Action** | `VERIFICATION_ACTION` | Confirm physical barrier integrity, test-before-touch zero energy, or atmospheric levels before work continuation or closure. | `HIGH` / `MEDIUM` |
| **D. Corrective Action** | `CORRECTIVE_ACTION` | Rectify root physical conditions or address identified low-energy workplace defects via standard work orders. | `MEDIUM` / `LOW` |
| **E. Preventive Action** | `PREVENTIVE_ACTION` | Systemic barrier audits, contractor pre-qualification reviews, or inspection cadence updates to prevent recurrence. | `LOW` |
| **F. Escalation Action** | `ESCALATION_ACTION` | Trigger formal organizational incident investigation or management review for high-consequence barrier breaches. | `HIGH` |
| **G. Positive Learning Action** | `POSITIVE_LEARNING_ACTION` | Document and share cases where direct engineered controls successfully arrested energy and saved lives. | `LOW` / `INFO` |

---

## 4. Reasoning State Action Matrix

Actions dynamically reflect Foresight's internal reasoning state:

| Internal Reasoning State | Allowed Action Types | Disallowed Actions | Operational Behavior |
|---|---|---|---|
| **`PSIF_PATHWAY_OPEN`** | `IMMEDIATE_ACTION`, `CONTROL_RESTORATION`, `VERIFICATION_ACTION`, `CORRECTIVE_ACTION`, `ESCALATION_ACTION`, `PREVENTIVE_ACTION` | `POSITIVE_LEARNING_ACTION` | Full emergency barrier response suite; immediate exposure halt; formal HSE investigation escalation. |
| **`HIGH_ENERGY_CONTROLLED`** | `POSITIVE_LEARNING_ACTION`, `VERIFICATION_ACTION` (Post-Arrest Inspection) | `IMMEDIATE_ACTION` (Stop Work), `ESCALATION_ACTION` | Recognizes capacity and barrier performance. Does NOT generate emergency stop work or unwarranted corrective actions. |
| **`LOW_ENERGY`** | `CORRECTIVE_ACTION` (Routine Maintenance), `PREVENTIVE_ACTION` (Walkthrough) | `IMMEDIATE_ACTION`, `ESCALATION_ACTION` | Proportionate maintenance; avoids catastrophic escalations for minor housekeeping anomalies. |
| **`INSUFFICIENT_INFORMATION`** | `VERIFICATION_ACTION` (Investigation & Fact-Finding) | `IMMEDIATE_ACTION`, `CORRECTIVE_ACTION` | Targets missing factual dimensions (worker position, control state, barrier integrity); no invented facts. |
| **`CONFLICTING_EVIDENCE`** | `VERIFICATION_ACTION` (Physical Record Reconciliation, Human Review) | Unilateral corrective actions | Neutral fact-finding and physical site reconciliation; never assumes either contradictory assertion is true. |

---

## 5. Control-State Action Mapping

Actions adapt strictly to the observed state of the critical direct control:

```
Control State: EFFECTIVE
  └── Action: Do NOT generate punitive corrective actions.
  └── Action: Document barrier performance in site register (Positive Learning).
  └── Action: Inspect barrier for deformation/fatigue prior to next duty cycle.

Control State: PARTIALLY_EFFECTIVE
  └── Action: Evaluate barrier degradation; strengthen or re-engineer barrier capacity.

Control State: ABSENT
  └── Action: Establish required direct engineered control before proceeding.
  └── Action: Review Start Work Checks and pre-job hazard analysis.

Control State: FAILED
  └── Action: Immediate operational halt; quarantine failed equipment.
  └── Action: Control restoration with certified engineered component.
  └── Action: Non-destructive testing and verification prior to return to service.

Control State: BYPASSED
  └── Action: Immediate halt; reinstate bypassed interlock or safety guard.
  └── Action: Escalate for permit violation and bypass authorization review.

Control State: NOT_VERIFIED
  └── Action: Perform zero-energy test / physical verification before touch.
  └── Action: Do NOT assert definitive equipment failure without physical evidence.

Control State: INCORRECTLY_ASSUMED
  └── Action: Re-identify equipment isolation points against P&IDs / single-line diagrams.
  └── Action: Perform mandatory test-before-touch verification.

Control State: RESTORED_BEFORE_EXPOSURE
  └── Action: Recognize operational pre-job check effectiveness (Positive Learning).
  └── Action: Evaluate whether inspection procedure or maintenance cycle warrants enhancement.

Control State: RESTORED_AFTER_EXPOSURE
  └── Action: Preserved as post-exposure restoration; does NOT negate previous exposure.
  └── Action: Full corrective and escalation response required.

Control State: PLANNED_ONLY
  └── Action: Quarantine planned control; treated as unverified/absent for the historical event.

Control State: RECOMMENDATION_ONLY
  └── Action: Post-incident recommendation text quarantined; not treated as event-time barrier failure.

Control State: UNKNOWN
  └── Action: Evidence-gathering verification action (interview personnel, inspect physical site).
```

---

## 6. Fifteen Hazard Family Direct Control Catalog

The Action Engine implements tailored direct control and verification actions across all 15 industry hazard families:

1. **Working at Height (`working_at_height`)**
   - *Immediate:* Halt elevated work & evacuate unprotected fall zones.
   - *Restoration:* Install certified anchorage (≥22.2 kN) and 100% tie-off dual lanyards with energy absorbers.
   - *Verification:* Inspect harness webbing, snap hook gate locks, and anchor structural certification.
2. **Suspended Loads / Cranes (`suspended_loads`)**
   - *Immediate:* Clear crane hoisting radius and halt lift operations.
   - *Restoration:* Re-rig load with rated wire rope/chain slings and tag lines; establish physical exclusion barricades.
   - *Verification:* Verify crane load chart margin, sling test certificates, and positive exclusion zone standoff.
3. **Line of Fire / Projectiles (`line_of_fire`)**
   - *Immediate:* Remove personnel from release trajectory & blast radius.
   - *Restoration:* Install whip checks across high-pressure couplings and fit rated deflection shields.
   - *Verification:* Verify whip checks have zero slack and deflection shields intercept calculated 45° discharge cone.
4. **Stored Pressure (`pressure_stored`)**
   - *Immediate:* Depressurize and halt live intervention until positive isolation is established.
   - *Restoration:* Install double block and bleed (DBB) or spectacle blind flanges with rated gasket.
   - *Verification:* Vent casing bleeder valves to zero gauge pressure and lock out bleeder ports.
5. **Electrical Energy (`electrical`)**
   - *Immediate:* Open upstream feeder breaker and lock out power distribution panel.
   - *Restoration:* Establish formal LOTO on all isolation points and apply grounding clusters.
   - *Verification:* Perform calibrated test-before-touch absence-of-voltage test across all phases.
6. **Mobile Equipment / Traffic (`vehicle_mobile_equipment`)**
   - *Immediate:* Immobilize mobile plant, engage parking brakes, and clear vehicle envelope.
   - *Restoration:* Install crash-rated physical segregation bollards and rectify reversing radar/alarms.
   - *Verification:* Test reversing alarm (>85 dB(A)), proximity radar, and operator line-of-sight segregation.
7. **Rotating Equipment & Pinch Points (`rotating_equipment`)**
   - *Immediate:* Depress emergency stop (E-stop) push button and de-energize machinery drive.
   - *Restoration:* Install fixed interlocked metal enclosure guards around rotating shafts and nips.
   - *Verification:* Confirm interlock switches actuate immediate machine trip when guard is opened.
8. **Hot Work Ignition (`hot_work_ignition`)**
   - *Immediate:* Extinguish hot work ignition sources and cut torch/welder power.
   - *Restoration:* Install fire-retardant containment blankets and stage continuous fire watch with extinguisher.
   - *Verification:* Perform 4-gas atmospheric testing (0% LEL) within 15-meter spark perimeter.
9. **Confined Space (`confined_space`)**
   - *Immediate:* Order immediate evacuation of confined space and deploy mechanical ventilation.
   - *Restoration:* Positively isolate all incoming lines with slip blinds and run continuous positive air extraction.
   - *Verification:* Measure oxygen (19.5%–23.5%), toxic gas (0 ppm H2S/CO), and explosive limits at 3 vertical levels.
10. **Chemical & Flammable Release (`chemical_flammable`)**
    - *Immediate:* Trip Emergency Shutdown (ESD) valve and evacuate personnel crosswind/upwind.
    - *Restoration:* Replace blown valve gaskets, close upstream isolation valves, and deploy water spray curtains.
    - *Verification:* Perform sniff testing and thermal imaging to confirm hydrocarbon seal integrity.
11. **Toxic & Asphyxiant Atmosphere (`toxic_atmosphere`)**
    - *Immediate:* Don 15-minute emergency escape breathing apparatus (EEBA) and evacuate crosswind.
    - *Restoration:* Reinstate cascade supplied air system and bump-test all personal gas monitors.
    - *Verification:* Check cascade breathing air manifold pressures and verify zero sensor drift with test gas.
12. **Thermal Energy (Steam / Cryogenic) (`thermal_energy`)**
    - *Immediate:* Isolate main steam / cryogenic supply valve and cordon off burn hazard zone.
    - *Restoration:* Reinstall calcium silicate thermal insulation blankets and repair steam trap seals.
    - *Verification:* Measure outer surface temperatures with calibrated infrared pyrometer (<60°C).
13. **Stored Mechanical / Spring Energy (`stored_mechanical_energy`)**
    - *Immediate:* Cease actuator work and pin mechanical counterweights.
    - *Restoration:* Install certified mechanical locking pins and safety clamping collars across actuator stroke.
    - *Verification:* Relieve residual spring tension and verify mechanical locking pins are fully seated.
14. **Excavation & Ground Collapse (`excavation_ground_collapse`)**
    - *Immediate:* Evacuate trench immediately and halt heavy machinery operating within 5 meters.
    - *Restoration:* Install certified aluminum hydraulic shoring shields or bench trench at 1:1.5 slope.
    - *Verification:* Confirm ladder egress is located within 7.5 meters of all workers and inspect spoil setback (≥1m).
15. **Dropped Objects (`dropped_objects`)**
    - *Immediate:* Clear overhead drop zone and halt elevated rigging activities.
    - *Restoration:* Install secondary tool tethering lanyards, toe-boards, and heavy-duty drop safety netting.
    - *Verification:* Inspect tool tethering attachment points (100% tie-off) and confirm drop netting integrity.

---

## 7. IOGP Life-Saving Rules Alignment & Separation

Foresight explicitly aligns its actions with IOGP Report 459 (Life-Saving Rules) and Start Work Checks while enforcing strict conceptual boundaries:

```
[IOGP Rule Match]   ── DOES NOT EQUAL ──>   [IOGP Rule Violation]
[IOGP Rule Match]   ── DOES NOT EQUAL ──>   [PSIF Potential]
[IOGP Violation]    ── DOES NOT EQUAL ──>   [Automatic PSIF Potential]
```

- **Rule Matched:** Indicates work type applicability (e.g. Work at Height, Energy Isolation, Bypassing Safety Controls).
- **Rule Violated:** Requires affirmative evidence that the mandatory direct barrier was compromised.
- **PSIF Potential:** Requires that a worker was in the credible release or exposure path of high energy.

Where IOGP rules apply, action templates utilize standardized IOGP Start Work Checks as explicit verification steps.

---

## 8. Qualitative Prioritization & Proportionality

Foresight strictly prohibits synthetic, invented numeric risk formulas (e.g. `P × C = 17.4`). Prioritization is qualitative, explainable, and grounded in structured evidence:

- **`CRITICAL`**: Active ongoing worker exposure, uncontrolled high energy, or open consequence pathway. Immediate operational cessation required.
- **`HIGH`**: Failed, absent, or bypassed direct barrier under high-energy potential. Work resumption barred until barrier is restored and independently verified.
- **`MEDIUM`**: Verification of unconfirmed barrier status, equipment inspection, or moderate procedural control strengthening.
- **`LOW`**: Routine maintenance work orders, minor surface repairs, standard monthly walkthroughs, or positive control learning dissemination.
- **`INFO`**: Barrier register documentation and safety bulletin sharing.

### Proportionality Enforcement
- Low-energy anomalies (e.g. minor housekeeping defects, low fluid drips) produce routine maintenance actions (`LOW` urgency) and never trigger facility shutdowns.
- PSIF open pathways produce immediate cessation and barrier restoration actions (`CRITICAL` and `HIGH` urgency) and are forbidden from offering "refresher training" as the sole action.

---

## 9. Action Deduplication & Multi-Hazard Consolidation

When an incident involves multiple hazard pathways (e.g., hot work + hydrocarbon release + line of fire), the Action Engine:
1. Gathers sub-pathway catalog actions across all detected energy types.
2. Deduplicates actions by operational intent (`STOP_WORK`, `RESTORE_BARRIER`, `VERIFY_ENERGY`, `ESCALATE_SIF`, `POSITIVE_LEARNING`).
3. Merges multi-hazard attributions into a unified card (e.g. `hazard: "hot_work_ignition, chemical_flammable, line_of_fire"`).
4. Unifies verification steps while eliminating redundant steps.
5. Inherits the highest qualitative urgency tier across merged components.
6. Renders a concise, non-repetitive action list sorted strictly by Category Order and Urgency.

---

## 10. Action Explanation Schema Contract

Every action recommendation emitted by Foresight satisfies the complete 14-field contract, enabling the UI to answer *"Why did Foresight recommend this?"* without calling an LLM:

```json
{
  "action_id": "ACT-WAH-IMM-01",
  "title": "Halt Elevated Work & Evacuate Unprotected Fall Zone",
  "action_type": "IMMEDIATE_ACTION",
  "category": "IMMEDIATE_ACTION",
  "urgency": "CRITICAL",
  "priority": "CRITICAL",
  "description": "Immediately order workers down from elevated structures lacking 100% tie-off or edge protection.",
  "reason": "Direct worker exposure to gravity fall hazard exceeding 1.8m without verified fall arrest protection.",
  "triggering_evidence": "Worker on scaffold edge without lifeline attached.",
  "hazard": "working_at_height",
  "control": "Full Body Harness & 100% Dual Tie-off",
  "control_addressed": "Full Body Harness & 100% Dual Tie-off",
  "control_state": "FAILED",
  "applicable_rule": "IOGP Working at Height",
  "rule_addressed": "IOGP Working at Height",
  "verification_steps": [
    "Confirm all elevated work has ceased and personnel are grounded",
    "Erect red warning tags ('DANGER: DO NOT USE') at all scaffold access points"
  ],
  "verification_method": [
    "Confirm all elevated work has ceased and personnel are grounded",
    "Erect red warning tags ('DANGER: DO NOT USE') at all scaffold access points"
  ],
  "source": {
    "source_id": "IOGP_REPORT_459_2018",
    "provenance_tier": "IOGP_GUIDANCE",
    "document": "IOGP Report 459 (Working at Height)",
    "section": "Rule 3: Working at Height Direct Controls",
    "verifiable": true
  },
  "provenance": {
    "source_id": "IOGP_REPORT_459_2018",
    "provenance_tier": "IOGP_GUIDANCE",
    "document": "IOGP Report 459 (Working at Height)",
    "section": "Rule 3: Working at Height Direct Controls",
    "verifiable": true
  },
  "hierarchy_level": "DIRECT_ENGINEERED_CONTROL",
  "target_barrier": "Full Body Harness & 100% Dual Tie-off",
  "regulatory_reference": null,
  "library_version": "action_library_v1"
}
```

---

## 11. Source Provenance & Audit Classification

All action recommendations maintain rigorous provenance attribution:
- **`IOGP_GUIDANCE`**: Derived from IOGP Report 459 Life-Saving Rules and Start Work Checks.
- **`REGULATORY_STANDARD`**: Grounded in OSHA 1910 / 1926 or Indian Oil Industry Safety Directorate (OISD) guidelines (e.g. OISD-GDN-192).
- **`DOMAIN_SIF_FRAMEWORK`**: Grounded in Edison Electric Institute Safety Classification and Learning (EEI SCL) capacity principles.
- **`FORESIGHT_ANALYTICAL`**: Evidence-completion, contradiction reconciliation, and multi-hazard consolidation protocols developed by Foresight. Explicitly tagged as Foresight Analytical guidance so it is never misrepresented as official regulatory directives.

---

## 12. API Endpoints & Workbench Integration

Two primary endpoints expose the grounded action engine payload to frontend clients and investigative workbenches:

1. **Dedicated Actions API:**
   `GET /api/incidents/<uuid:pk>/actions/`
   Returns the prioritized action plan, methodology notice, library version, and incident metadata.

2. **Unified Reasoning API:**
   `GET /api/incidents/<uuid:pk>/reasoning/`
   Includes `grounded_actions` directly in the payload alongside `action_interface` and step-by-step reasoning traces. No frontend reconstruction is required.

---

## 13. Test Verification Suite Summary

Test Suite: `tests/test_action_engine.py` (42 / 42 Tests Passed)

| Test Class | Test Count | Key Invariants Verified |
|---|---|---|
| `TestFifteenHazardFamilyActionCoverage` | 30 | All 15 hazard families generate tailored immediate and restoration actions under open PSIF pathways; all 15 generate positive control learning under controlled capacity. |
| `TestReasoningStateActionMatrix` | 5 | All 5 internal states (`PSIF_PATHWAY_OPEN`, `HIGH_ENERGY_CONTROLLED`, `LOW_ENERGY`, `INSUFFICIENT_INFORMATION`, `CONFLICTING_EVIDENCE`) produce strictly compliant action sets. |
| `TestActionDeduplicationAndMultiHazard` | 2 | Multi-hazard stop-work actions merge into unified cards; identical action IDs deduplicate verification steps and inherit maximum urgency. |
| `TestActionSchemaAndTraceability` | 1 | Verifies complete 14-field contract on all generated actions. |
| `TestAntiInferenceAndQuarantineLeakage` | 2 | Proves modifying corrective action text has zero impact on PSIF decision; recommendation-only text does not trigger false failure actions. |
| `TestActionAPIEndpoints` | 2 | Live HTTP integration tests verifying `/actions/` and `/reasoning/` endpoints deliver valid grounded action payloads. |

---

## 14. Remaining Limitations & Non-Goals

1. **No Facility-Specific Automation:** The engine does not generate specific equipment tag numbers (e.g. "V-104A") unless explicitly present in the incident record.
2. **No Automated Permit Approval:** The engine suggests verification steps and review actions; it does not replace site-specific Permit to Work (PTW) authorizer workflows.
3. **No Dynamic Cost Estimation:** The engine qualitatively assesses operational priority; it does not calculate monetary repair costs.
