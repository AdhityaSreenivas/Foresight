# Admin Flow — Barrier Intelligence Portfolio (IOGP Classification Redesign)

## Overview & Purpose
The **Barrier Intelligence Portfolio** redesign replaces the tabular listing of IOGP Life-Saving Rules on the Admin Flow IOGP Classification page (`/admin-flow/iogp/`) with an interactive, high-density 9-card visual portfolio.

Admin Flow is the evaluator demonstration workflow for Problem Statement 26165 (*AI/NLP Engine to Detect Serious Injury & Fatality Precursors*). The Barrier Intelligence Portfolio provides immediate situational awareness across all 9 canonical Life-Saving Rules while rigorously adhering to non-causal safety semantics and hard workspace isolation.

---

## Strict Scope & Invariant Guarantees
1. **Isolated to Admin Flow**: Changes apply strictly to `/admin-flow/iogp/`. Regular/global IOGP Classification and Barrier Intelligence pages (`/dashboard/barriers/`) remain completely untouched.
2. **Preserved First Graph**: The top chart, **“IOGP Barrier Risk Distribution Comparison”** (`#adminFlowIOGPChart`), remains intact with its exact data logic, dual-series bar layout (Matched Observations vs. PSIF-Linked Candidates), and visual styling.
3. **No N+1 Query Regression**: Aggregation uses single bulk-grouped ORM queries (`Count`, `filter`, `select_related`) across the 9 rules rather than individual database queries per card.
4. **Clean-Sheet Reset Compatibility**: Integrated directly with `reset_admin_flow_workspace()`. On reset, generation tokens bump and all 9 cards return to `0` counts with zero stale cache.
5. **No Data Loss**: Unmatched observations (records legitimately matching no IOGP rule) are presented in a dedicated reconciliation coverage banner below the 9 cards.

---

## The 9 Canonical IOGP Life-Saving Rules
The portfolio contains exactly the 9 canonical rules defined in IOGP Report 459 (2018), arranged by default in official canonical order:

1. **Bypassing Safety Controls** — *Obtain authorization before overriding or disabling safety-critical equipment.*
2. **Confined Space** — *Obtain authorization before entering a confined space; test atmosphere and verify isolation.*
3. **Driving** — *Always wear seatbelts, obey speed limits, avoid distractions, and inspect vehicles.*
4. **Energy Isolation** — *Verify isolation and zero energy state before work begins; apply Lockout/Tagout (LOTO).*
5. **Hot Work** — *Identify and control ignition sources, obtain hot work permits, and monitor for flammables.*
6. **Line of Fire** — *Position yourself clear of moving machinery, under suspended loads, and tensioned lines.*
7. **Safe Mechanical Lifting** — *Ensure lifting equipment is certified, load is within capacity, and exclusion zone is secure.*
8. **Work Authorization** — *Work with a valid permit when required; understand scope, hazards, and controls.*
9. **Working at Height** — *Protect yourself against falling when working at height (≥ 1.8m or per site standard).*

No rules are added, removed, or renamed.

---

## Card Structure & Visual Hierarchy
Each card is self-contained with a responsive layout (3 columns on desktop, 2 on tablet, 1 on mobile):

```
┌─────────────────────────────────────────────────────────┐
│ [SVG ICON]                                     Rule #4  │
│                                                         │
│ Energy Isolation                                        │
│                                                         │
│ 42                                                      │
│ MATCHED OBSERVATIONS                                    │
│                                                         │
│ ─────────────────────────────────────────────────────── │
│ PSIF-Linked                 Affected Locations          │
│ 27                          6                           │
│                                                         │
│ ─────────────────────────────────────────────────────── │
│ 64.3% PSIF-rate                      View Details  →    │
└─────────────────────────────────────────────────────────┘
```

### Visual Priority
1. **Rule Name**: Bold, high-contrast title.
2. **Matched Observations (Hero Number)**: Visually prominent (2.25rem, 800 weight, monospace numbers).
3. **Secondary Sub-Metrics**:
   - **PSIF-Linked**: Count of matched records predicted as PSIF (highlighted in critical red if > 0).
   - **Affected Locations**: Distinct normalized internal facilities/sites.
4. **Action Footer**: Linkage rate percentage and "View Details →" button.

---

## Metric Definitions & Semantic Safety

### Approved Terminology
| Metric Name | Authoritative Definition |
| :--- | :--- |
| **Matched Observations** | Distinct Admin Flow incidents linked to the IOGP rule by the canonical deterministic keyword matching engine. |
| **PSIF-Linked Observations** | Matched Admin Flow incidents with canonical model prediction = PSIF (subject to sparse input eligibility). |
| **Affected Internal Locations** | Distinct normalized internal locations represented among matched Admin Flow incidents. |
| **Most Frequently Associated Activity** | Most common reported `job_task` among matched incidents for this rule. |
| **Highest Observation Concentration** | Internal location with the highest frequency of matched observations. |
| **Dominant Observed Control State** | Highest-frequency evidence-based control condition (`Effective`, `Failed`, `Absent`, `Bypassed`). UNKNOWN is never treated as failure. |

### Prohibited Causal Terminology
The system strictly enforces non-causal language across all UI elements and API payloads:
- **Forbidden**: *"barrier caused"*, *"confirmed violation"*, *"failure probability"*, *"risk probability"*, *"100% confidence"*, *"most dangerous location/activity"*.
- **Mandatory Methodology Disclaimer**:
  > *“IOGP categories are derived from the canonical rule-matching system. A rule match does not by itself establish a confirmed violation or control failure.”*

---

## Interactive Detail View (Inline Modal)
Clicking any card or pressing Enter/Space opens an inline detail modal dialog with zero page reload:

1. **Header**: Rule icon, title, Rule #, and citation (`IOGP Report 459 (2018)`).
2. **Intent Box**: Official IOGP rule intent statement.
3. **4-Metric Grid**: Matched Observations, PSIF-Linked, Affected Sites, PSIF Linkage Rate.
4. **Operational Pattern Analysis**:
   - Most frequently associated activity (`job_task`) with record count.
   - Highest observation concentration (`location`) with record count.
5. **Control State Signal**: Evidence-based condition with note that unknown states remain unclassified.
6. **Canonical Start-Work Checks**: Specific verification steps required prior to commencing work.
7. **Representative Matched Incidents**: List of up to 4 recent demonstration observations with date, task, location, description snippet, PSIF badge, and direct link to `/admin-flow/incidents/<id>/`.
8. **Scoped Drilldown Action**: Dedicated button navigating to `/admin-flow/incidents/?rule=<rule>` ensuring zero global record leakage.

---

## Card Sorting Controls
Interactive sort pill tabs permit sorting the 9 cards dynamically:
- **Canonical Order** (default): Rule 1 through Rule 9.
- **Matched Observations**: Descending count of matched incidents.
- **PSIF-Linked**: Descending count of PSIF precursor linkages.
- **Affected Locations**: Descending count of affected internal facilities.

---

## REST API Specification
Exposed at `GET /admin-flow/api/iogp/portfolio/`:

### Query Parameters
- `rule` (optional): Filter to a specific canonical rule name (e.g. `?rule=Energy Isolation`).

### Response Schema (`200 OK`)
```json
{
  "status": "success",
  "has_data": true,
  "total_analyzed_incidents": 42,
  "total_rule_matches": 58,
  "matched_incidents_count": 38,
  "unmatched_incidents_count": 4,
  "total_psif_linked": 16,
  "rules": [
    {
      "order": 4,
      "rule": "Energy Isolation",
      "slug": "energy-isolation",
      "modal_id": "modal-rule-4",
      "description": "Verify isolation and zero energy state before work begins...",
      "source_reference": "IOGP Report 459 (2018) Energy Isolation",
      "start_work_checks": [
        "I have identified all sources of energy (electrical, mechanical, fluid)",
        "I have confirmed energy is isolated, locked, and tagged",
        "I have tested for zero energy state"
      ],
      "matched_observations": 12,
      "formatted_matched": "12",
      "psif_linked_observations": 7,
      "formatted_psif_linked": "7",
      "psif_linkage_rate": 58.3,
      "affected_locations": 3,
      "formatted_affected_locations": "3",
      "top_activity": "Compressor Valve Replacement",
      "top_activity_count": 5,
      "top_location": "Compressor Station 3",
      "top_location_count": 8,
      "dominant_control_state": "Bypassed / Defeated (3 observations)",
      "control_signal": "Reported evidence indicates dominant state: Bypassed / Defeated",
      "has_matches": true,
      "recent_incidents": [...]
    }
  ],
  "unmatched_summary": {
    "rule": "No IOGP Rule Matched",
    "matched_observations": 4,
    "psif_linked_observations": 0,
    "affected_locations": 2
  },
  "methodology_note": "IOGP categories are derived from the canonical rule-matching system. A rule match does not by itself establish a confirmed violation or control failure.",
  "workspace_id": "admin_flow",
  "generation": 3
}
```

---

## Caching & Invalidation Architecture
- **Cache Key**: `admin_flow:barrier_portfolio:{generation}`
- **TTL**: 1800 seconds (30 minutes).
- **Invalidation Triggers**:
  - `reset_admin_flow_workspace()`: Bumps `ADMIN_FLOW_GENERATION_KEY` and invalidates old keys.
  - Manual report submission (`/admin-flow/submit/`).
  - Batch dataset upload & processing (`/admin-flow/upload/`).

---

## Testing & Quality Assurance
Automated test suite in `tests/test_admin_flow_iogp_portfolio.py`:
- `test_zero_state_renders_nine_cards_with_zero_counts`: PASS
- `test_real_data_aggregations_and_card_metrics`: PASS
- `test_api_portfolio_endpoint`: PASS
- `test_global_isolation`: PASS
- `test_reset_clears_barrier_portfolio`: PASS
- `test_prohibited_terminology_audit`: PASS
- `test_regular_login_global_barrier_page_unaffected`: PASS
