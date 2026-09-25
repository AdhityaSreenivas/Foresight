# Barrier & Critical-Control Intelligence Specification (V1)
**SIH Problem Statement 26165 — Task 11 Engineering Document**

---

## 1. Executive Summary & Core Safety Methodology

The Foresight platform integrates Barrier & Critical-Control Intelligence to provide an evidence-grounded, defensible bridge between incident observations, operational high-energy hazards, and canonical safety rules. 

Across enterprise E&P operations and historical incident datasets, structured control condition fields (e.g. whether a barrier was physically functioning, missing, or breached) are largely unpopulated, blank, or recorded as "unknown". Consequently, **V1 strictly prohibits synthetic control health estimation or inferring barrier degradation from keyword mentions alone.**

### The Core Invariant
> **"Barrier intelligence links observations to canonical safety-rule domains and evidence-supported control states. Rule matching alone does not establish a control failure or barrier effectiveness."**

A mention such as *"Lockout procedure was followed and zero energy verified before breaking flange"* represents an observation within the **Energy Isolation** safety domain; it is **not** an Energy Isolation failure. Conversely, explicit evidence such as *"Isolation breaker was bypassed without authorization"* supports a control state of `COMPROMISED`.

---

## 2. Authoritative V1 Metrics & Exact Mathematical Definitions

V1 restricts platform-wide reporting to four authoritative, defensible metrics:

| Metric Name | Exact Mathematical Definition | Interpretation Boundary |
| :--- | :--- | :--- |
| **Matched Observations** | Distinct incidents linked to a canonical IOGP rule through deterministic keyword and phrase matching: $Count(Distinct(IncidentID))$ where rule is matched. | Measures operational frequency and hazard domain representation. Does **not** indicate non-compliance or failure. |
| **PSIF-Linked Observations** | Matched incidents meeting three strict eligibility conditions: (1) $psif\_predicted = True$, (2) $is\_sparse\_input = False$, and (3) incident remains valid for analysis. | Sub-population of matched events carrying high potential for serious injury or fatality under current operational conditions. |
| **Affected Sites** | Distinct non-blank normalized geographical sites/locations among matched observations: $Count(Distinct(NormalizedSite))$ where $Site \neq \emptyset$ and $Site \neq None$. | Extent of geographical/operational distribution across rigs, production batteries, drill sites, and gas plants. |
| **PSIF-Linkage Rate** | Exact ratio: $\frac{\text{PSIF-Linked Matched Observations}}{\text{Matched Observations}} \times 100\%$ | Proportion of hazard observations meeting PSIF risk criteria. Must **never** be labeled as "probability of barrier failure" or "control failure rate". |

### Mandatory Display Label
All dashboard views, tooltips, and API responses must explicitly format the rate as:
$$\text{"X.X\% of matched observations were PSIF-linked by the active model"}$$

---

## 3. Canonical 9 IOGP Life-Saving Rules Domain Model

The platform strictly recognizes the **9 Canonical IOGP Life-Saving Rules** (Report 459 standard). No tenth or synthetic rule may be introduced.

| # | Canonical Rule Name | Hazard & Energy Domain | Primary Critical Safeguard |
|---|:---|:---|:---|
| 1 | **Bypassing Safety Controls** | Operating without safety critical equipment | Interlocks, gas detectors, relief valves, safety trips |
| 2 | **Confined Space** | Toxic, oxygen-deficient, or engulfment atmosphere | Continuous gas testing, standby watch, breathing apparatus |
| 3 | **Driving** | Kinetic energy from light/heavy transport | Speed management, seatbelts, route hazard assessment |
| 4 | **Energy Isolation** | Electrical, hydraulic, pneumatic, mechanical energy | Lockout/Tagout (LOTO), blind flange isolation, zero-energy test |
| 5 | **Hot Work** | Flammable atmosphere, ignition sources | Spark containment, continuous LEL atmospheric monitoring |
| 6 | **Line of Fire** | Suspended loads, high-pressure releases, trajectory | Exclusion zones, barricades, standing outside release vector |
| 7 | **Safe Mechanical Lifting** | Gravitational potential of heavy suspended equipment | Certified lifting gear, lift plan, rigger verification |
| 8 | **Work Authorization** | Concurrent or high-risk operational tasks | Valid permit-to-work (PTW), Start Work Checks, SIMOPS signoff |
| 9 | **Working at Height** | Fall potential exceeding 1.8m | 100% tie-off harness, inspected scaffolding, edge protection |

---

## 4. Control States & Explicit Semantic Requirements

The domain model distinguishes five explicit internal control semantics:

```
                  ┌─────────────────────────────────┐
                  │ Source Incident Observation     │
                  └────────────────┬────────────────┘
                                   │
              ┌────────────────────┴────────────────────┐
              │ Is explicit evidence available?         │
              └────────┬───────────────────────┬────────┘
                      YES                      NO
                       │                       │
      ┌────────────────┴───────────────┐       ▼
      │ What does explicit proof show? │   ┌───────────────────────┐
      └───────┬─────────┬──────────────┘   │ UNKNOWN               │
              │         │                  │ Evidence: "Control    │
     Effective│         │Bypassed/Breached │ effectiveness could   │
              ▼         ▼                  │ not be established    │
┌────────────┐   ┌─────────────┐           │ from source data."    │
│ CONTROLLED │   │ COMPROMISED │           └───────────────────────┘
└────────────┘   └─────────────┘
              │
       Both   │ (e.g. held then bypassed)
              ▼
┌─────────────────────┐
│ PARTIALLY_EFFECTIVE │
└─────────────────────┘
```

1. **`CONTROLLED`**: Explicit source evidence confirms that the engineered or procedural control functioned as intended and mitigated the energy release (e.g., *"zero energy verified"*, *"wore full body harness which arrested fall"*, or structured `control_condition = 'effective'`).
2. **`COMPROMISED`**: Explicit source evidence confirms the control was bypassed, missing, defective, or breached (e.g., *"isolation was bypassed"*, *"breaker unlatched without permit"*, or structured `control_condition in ['failed', 'bypassed', 'absent']`).
3. **`PARTIALLY_EFFECTIVE`**: Explicit source evidence indicates that some controls functioned while secondary controls were compromised (e.g., *"relief valve popped but secondary containment overflowed"*).
4. **`UNKNOWN`**: Default state when structured fields are null/blank/unknown and narrative text contains no explicit control failure or success claims. Evidence statement: *"Control effectiveness could not be established from available source data."* Missing information must **never** be coerced into `COMPROMISED`.
5. **`NOT_APPLICABLE`**: Energy or hazard was not present.

---

## 5. Evidence-Grounded 7-Stage Barrier Linkage

Each incident is evaluated through a strict 7-stage causal progression:

$$\text{Incident} \longrightarrow \text{Hazard / Energy} \longrightarrow \text{Exposure} \longrightarrow \text{Critical Control} \longrightarrow \text{Control State} \longrightarrow \text{IOGP Rule} \longrightarrow \text{PSIF Pathway}$$

Every linkage record preserves:
- **`source_field`**: The exact database column providing evidence (e.g. `composite_narrative`, `control_condition`, `energy_type`).
- **`source_text` / span**: The verbatim narrative excerpt or structured enum.
- **`normalized_concept`**: Standardized ontology term.
- **`reason_method`**: Traceable classification rule (`deterministic_evidence_grounded`).
- **`state`**: Evaluated `ControlSemantics`.

---

## 6. Action Engine & Corrective Action Integration

The Barrier Intelligence service interfaces directly with the Task 6 Action Engine. Corrective actions are strictly conditioned on evaluated control evidence:

### Energy Isolation Safeguard Contract
- **Scenario A: Energy Isolation + Explicit Compromise/Bypass Evidence**
  - Evaluated State: `COMPROMISED`
  - Action Code: `LOTO-VER-002`
  - Generated Action: *"Verify isolation/bypass-control compliance at the identified work activity."*
- **Scenario B: Energy Isolation + No Control Evidence (Field Blank/None)**
  - Evaluated State: `UNKNOWN`
  - Action Code: `LOTO-VER-001`
  - Generated Action: *"Verify isolation status and evidence of effective energy isolation."*
  - Anti-Inference Invariant: The system must **never** assert *"Isolation controls failed"*.

---

## 7. Investigation Workspace Integration

In the Task 9 Unified Investigation Workspace (`/incidents/<id>/`), Barrier Intelligence is exposed as a first-class card within the canonical reasoning result:
- Matched canonical rule names with classification cues (matched keywords, source field, rule method).
- Control state badge (`CONTROLLED`, `COMPROMISED`, `UNKNOWN`).
- Evidentiary text snippet or standardized unknown disclaimer.
- Evidence strength (`STRONG`, `MODERATE`, `WEAK`).
- PSIF pathway role (`Primary Barrier Precursor`, `Operational Hazard Context`, `Capacity / Controlled Energy`).
- Grounded action linkage.
- Fleet context (portfolio-wide matched observations, PSIF count, and linkage rate).

---

## 8. Performance, Query Optimization & Caching

### Query Strategy
The portfolio calculation processes over 560,000 incidents and 634,000 rule tags in a single SQL aggregation pass:
```python
IOGPRuleTag.objects.filter(rule__in=CANONICAL_IOGP_RULES).values("rule").annotate(
    matched_observations=Count("incident", distinct=True),
    psif_linked_observations=Count(
        "incident",
        filter=Q(
            incident__prediction__psif_predicted=True,
            incident__prediction__is_sparse_input=False,
        ),
        distinct=True,
    ),
    affected_sites=Count(
        "incident__location",
        filter=~Q(incident__location__in=[None, ""]),
        distinct=True,
    ),
)
```
- Total execution time on full dataset: **< 1.8 seconds**.
- No Python looping over incidents for portfolio metrics.
- Zero-division guard for empty datasets.

### Cache Strategy
- **Key**: `dashboard:barrier_intelligence:v1`
- **TTL**: 3600 seconds (1 hour)
- **Invalidation**: Integrated into `invalidate_analytics_cache()`. When new incidents are ingested, predictions refreshed, or batches deleted, the barrier intelligence cache is immediately purged.

---

## 9. Representative Incidents & Sampling Disclosure

When viewing rule details (`/dashboard/barriers/<rule_slug>/`), representative incidents are displayed with their evaluated control states.
- **Mandatory Sampling Disclosure**:
  > *"Representative incidents are illustrative examples matching this rule and are not statistically sampled across the population."*
- Paged results use database-level indexing (`order_by("-id")`) to prevent memory exhaustion.
