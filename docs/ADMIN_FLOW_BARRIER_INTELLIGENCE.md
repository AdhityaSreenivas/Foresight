# Admin Flow Barrier Intelligence Engine — Technical & Methodological Specification

## 1. Executive Summary & Foundational Principle

In previous iterations of the Admin Flow Pattern Analysis system, the **Barrier Patterns** page conflated IOGP Life-Saving Rules (e.g., *Working at Height*, *Energy Isolation*, *Safe Mechanical Lifting*, *Line of Fire*) with protective safeguards. This led to analytical distortion where high-level safety rules were erroneously presented as "critical controls" or "barriers".

This document formalizes the canonical **Barrier Intelligence Engine** for Admin Flow.

### The Canonical Principle of a Barrier
> **A barrier is the actual physical, engineered, operational safeguard, control, or human intervention described in an incident that prevents, stops, absorbs, mitigates, or limits a hazardous event from progressing to a more severe consequence.**

### Strict Dimensional Separation
The system strictly decouples the analytical dimensions:
1. **HAZARD**: The source of potential harm or high-energy release (e.g., Gravitational Potential Energy / Height, Stored Hydraulic Pressure, Moving Heavy Machinery).
2. **EXPOSURE**: The presence of personnel within the zone of danger (e.g., Worker on elevated scaffold, Technician in pressurized line discharge zone).
3. **EVENT / TRIGGER**: The mechanical failure or unintended release (e.g., Platform grating gave way, Flange gasket ruptured).
4. **BARRIER**: The actual protective safeguard (e.g., Safety Harness / Fall-Arrest System, Emergency Isolation Valve, Machine Guard).
5. **BARRIER STATE**: The operational condition of the safeguard during the incident (e.g., `EFFECTIVE`, `FAILED`, `ABSENT`, `BYPASSED`, `NOT_VERIFIED`, `PARTIALLY_EFFECTIVE`).
6. **CONSEQUENCE**: The actual injury or damage versus the potential unmitigated outcome (e.g., Fall arrested without impact vs. Fatal impact).
7. **IOGP RULE**: The high-level industry safety rule domain associated with the task (e.g., *Working at Height*, *Energy Isolation*).
8. **PSIF CLASSIFICATION**: Potential SIF determination produced independently by the authoritative PSIF reasoning engine.

---

## 2. Canonical Barrier Taxonomy

The engine defines a structured taxonomy of 28 distinct protective barrier categories:

| Category Code | Canonical Display Name | Default Role | Primary Mechanism |
| :--- | :--- | :--- | :--- |
| `FALL_ARREST_SYSTEM` | Safety Harness / Fall-Arrest System | Mitigative / Recovery | Arrests falling personnel, limits descent distance |
| `GUARDRAIL` | Guardrail / Edge Protection | Preventive | Physical perimeter barrier preventing fall exposure |
| `SAFETY_NET` | Safety Net / Catch Platform | Mitigative | Catches falling objects or personnel |
| `EXCLUSION_BARRIER` | Physical Exclusion Barricade | Preventive | Denies unauthorized physical access into hazardous zones |
| `MACHINE_GUARD` | Machine Guard / Equipment Shield | Preventive | Encloses pinch points, rotating shafts, and nip points |
| `INTERLOCK` | Safety Interlock / Light Curtain | Preventive | Trips power if protective boundary or door is breached |
| `EMERGENCY_STOP` | Emergency Stop / Trip Wire | Mitigative | Immediate emergency mechanical/electrical trip |
| `EMERGENCY_SHUTDOWN` | Emergency Shutdown System (ESD/ESDV) | Mitigative | Rapid automated plant/unit isolation and depressurization |
| `ISOLATION_VALVE` | Isolation Valve / Positive Mechanical Blind | Preventive | Positive mechanical barrier isolating hazardous fluids |
| `LOCKOUT_TAGOUT` | Lockout / Tagout (LOTO) | Preventive | Physical zero-energy padlocking preventing re-energization |
| `ZERO_ENERGY_VERIFICATION` | Zero-Energy Verification (Test-Before-Touch) | Preventive | Confirmatory test ensuring residual stored energy is dissipated |
| `PRESSURE_RELIEF` | Pressure Relief Valve (PRV) / Rupture Disk | Mitigative | Overpressure relief preventing vessel/piping rupture |
| `GAS_DETECTION` | Gas Detection / Atmospheric Monitoring | Detective | Continuous or pre-entry atmospheric toxic/flammable monitoring |
| `VENTILATION` | Mechanical Forced Air Ventilation | Mitigative | Dilutes hazardous atmospheres in enclosed spaces |
| `FIRE_SUPPRESSION` | Fire Suppression System / Auto-Deluge | Mitigative | Automatic or manual extinguishment of thermal releases |
| `FIRE_WATCH` | Dedicated Fire Watch & Extinguisher | Detective / Mitigative | Dedicated observer with ready extinguishing capability |
| `CONTAINMENT` | Spill Containment / Bund / Drip Pan | Mitigative | Retains released hazardous liquids |
| `VEHICLE_PEDESTRIAN_SEGREGATION` | Vehicle / Pedestrian Segregation Barrier | Preventive | Physical separation between moving vehicles and pedestrian routes |
| `SEAT_BELT` | Seat Belt / Restraint Harness | Mitigative | Restrains occupants during collision or vehicle rollover |
| `WHEEL_CHOCK` | Wheel Chocks / Parking Brake | Preventive | Secures vehicles/mobile machinery from unintended rollaway |
| `PROTECTIVE_SHIELD` | Protective Splash / Blast Shield | Mitigative | Deflects pressurized spray, flying chips, or thermal flash |
| `RIGGING_CONTROL` | Certified Rigging / Whip Check Safety Cable | Preventive / Mitigative | Secures suspended loads or captures pressurized hose whips |
| `LIFTING_EXCLUSION_ZONE` | Lifting Radius Exclusion Zone | Preventive | Enforces clear perimeter under and around crane suspended load |
| `RESCUE_SYSTEM` | Standby Rescue System / Retrieval Lifeline | Recovery / Rescue | Immediate retrieval capability for confined space or height emergency |
| `STOP_WORK_INTERVENTION` | Stop-Work Authority Intervention | Administrative / Preventive | Timely human intervention halting unsafe progress |
| `PPE_PROTECTIVE_BARRIER` | Task-Critical Protective Barrier PPE | Mitigative | Barrier-grade PPE (arc flash shield, chemical suit) absorbing energy |
| `OTHER_KNOWN_BARRIER` | Other Engineered Protective Measure | Preventive | Clear protective measure outside predefined taxonomy |
| `UNKNOWN` | No Established Protective Barrier | Unknown | No verifiable safeguard present or identified |

---

## 3. Barrier States & Operational Condition

The state of a barrier is decoupled from its identity. Mentioning a barrier never implies that it failed.

### Canonical States:
- **`EFFECTIVE`**: The barrier was installed, verified, and successfully prevented, arrested, absorbed, or mitigated the hazard progression.
- **`FAILED`**: The barrier was in place but degraded, severed, ruptured, passed, or mechanically broke under load.
- **`ABSENT`**: The barrier was completely omitted, missing, not installed, or unhooked.
- **`BYPASSED`**: The barrier was deliberately defeated, bridged with a jumper wire, overridden, or propped open.
- **`NOT_VERIFIED`**: The barrier was planned or assumed, but atmospheric testing or zero-energy check was skipped.
- **`PARTIALLY_EFFECTIVE`**: The barrier absorbed part of the energy but was inadequate for full containment (e.g. ventilation inadequate).
- **`INCORRECTLY_ASSUMED`**: A barrier was presumed active by the crew but did not exist in physical reality.
- **`RESTORED_BEFORE_EXPOSURE`**: A deficient barrier was recognized and made safe before exposure occurred.
- **`RESTORED_AFTER_EXPOSURE`**: The barrier was repaired or reinstated following the incident event.
- **`PLANNED_ONLY`**: The barrier appeared only in permit documentation without physical execution.
- **`UNKNOWN`**: State could not be established from available narrative evidence.

### Grouping for Analytical Integrity:
- **Effective Safeguards**: `EFFECTIVE`, `RESTORED_BEFORE_EXPOSURE`.
- **Deficient Signals**: `FAILED`, `ABSENT`, `BYPASSED`, `NOT_VERIFIED`, `INCORRECTLY_ASSUMED`, `PARTIALLY_EFFECTIVE`.
- **Neutral / Informational**: `UNKNOWN`, `PLANNED_ONLY`.

---

## 4. Barrier Roles

The engine classifies each barrier observation into one of 5 functional roles:
1. **`PREVENTIVE`**: Prevents the hazardous release or initiates hazard interruption before exposure occurs (e.g. Guardrail, Lockout/Tagout, Machine Guard).
2. **`DETECTIVE`**: Identifies the hazard and generates an alert before critical exposure (e.g. Gas Detector, Atmospheric Monitoring).
3. **`MITIGATIVE`**: Absorbs, limits, or controls the severity of the hazardous energy once released (e.g. Emergency Shutdown, Pressure Relief Valve, Safety Net).
4. **`RECOVERY_RESCUE`**: Restores safety or rescues personnel following hazard impact (e.g. Standby Rescue Winch, Fall-Arrest Suspension Lifeline).
5. **`ADMINISTRATIVE_STOP_WORK`**: Operational authority intervention interrupting work before high-energy consequence (e.g. Stop-Work Authority).

---

## 5. Semantic Extraction & Context-Aware Rules

The engine rejects naive keyword matching. It applies semantic pattern inspection:

### 1. Functional Verification vs. Pure Storage
- **Trigger**: "Safety harness"
- **Context A**: *"The worker started to fall, but his safety harness caught him and helped him regain balance."*
  - **Verdict**: Extracted as `FALL_ARREST_SYSTEM` with state `EFFECTIVE`.
- **Context B**: *"The harness was stored in the truck during the shift."*
  - **Verdict**: **Rejected**. Mere storage in a toolbox or vehicle is not evidence of a functioning barrier during an operational event.

### 2. Operational Evidence vs. Post-Incident Recommendations
- **Trigger**: "Guardrail"
- **Context A**: *"A guardrail section was missing and the worker slipped off the edge."*
  - **Verdict**: Extracted as `GUARDRAIL` with state `ABSENT`.
- **Context B**: *"The investigation team recommends installing guardrails along the walkway."*
  - **Verdict**: **Rejected**. Forward-looking corrective recommendations are post-event administrative desires, not barriers present during the incident.

### 3. Negation & Deficiency Parsing
- *"No guardrail was installed."* $\rightarrow$ Barrier: `GUARDRAIL`, State: `ABSENT`.
- *"The harness lanyard snapped during the fall."* $\rightarrow$ Barrier: `FALL_ARREST_SYSTEM`, State: `FAILED`.
- *"The safety interlock was bypassed with a jumper wire."* $\rightarrow$ Barrier: `INTERLOCK`, State: `BYPASSED`.
- *"Atmospheric testing was not verified before entry."* $\rightarrow$ Barrier: `GAS_DETECTION`, State: `NOT_VERIFIED`.

### 4. Multi-Barrier Coexistence
An incident narrative frequently describes multiple interacting safeguards:
- *"A rotating shaft was exposed because its guard had been removed. A worker reached toward the shaft but another employee activated the emergency stop before contact occurred."*
- **Observation 1**: `MACHINE_GUARD` $\rightarrow$ State: `ABSENT` (Pointers: guard removed).
- **Observation 2**: `EMERGENCY_STOP` $\rightarrow$ State: `EFFECTIVE` (Pointers: activated e-stop before contact).
The engine records both observations, attributing 1 incident to Machine Guard deficiency and 1 incident to Emergency Stop success.

---

## 6. Denominators & Counting Precision

To prevent mathematical distortion, metrics use explicit, defensible denominators:

1. **Total Workspace Incidents**: $N_{\text{total}}$ (All incidents in Admin Flow, e.g., 1,000).
2. **Barrier-Linked Incidents**: Distinct incidents where at least one canonical barrier was identified from evidence ($N_{\text{identified}}$, e.g., 957).
3. **Barrier Identification Rate**: $\frac{N_{\text{identified}}}{N_{\text{total}}} \times 100\%$ (e.g., 95.7%).
4. **Associated Incidents per Barrier**: Distinct incidents establishing that specific barrier category.
5. **Effective Safeguard Incidents**: Distinct incidents where the barrier state is `EFFECTIVE`.
6. **Deficient Safeguard Incidents**: Distinct incidents where the barrier state is deficient (`FAILED`, `ABSENT`, `BYPASSED`, `NOT_VERIFIED`, `PARTIALLY_EFFECTIVE`).

**Strict Rule**: An effective barrier is never tallied as a "failure" or "deficiency".

---

## 7. Performance & Caching Architecture

1. **Versioned Scoped Caching**:
   - Cache key: `admin_flow:barrier_patterns:{version}`.
   - Cache invalidation occurs automatically on incident upload, submission, reset, or pipeline execution via `invalidate_admin_flow_barrier_cache()`.
2. **One-Pass Batch Processing**:
   - Barrier observations are extracted across the queryset in memory with single-pass regex compilation.
   - Distinct sets of incident IDs are accumulated per category, ensuring zero duplicate incident counts.
   - Query latency is sub-50ms when cached, and under 600ms for a full 1,000-record dataset parse.
