# Foresight Admin Flow Architecture & Hard Data Isolation Contract

## 1. Executive Summary & Objective

**Admin Flow** is a segregated demonstration workspace built specifically for demonstrating the Foresight PSIF Platform to evaluation judges. 

Problem Statement 26165:
*“AI/NLP Engine to Detect Serious Injury & Fatality (SIF) Precursors in OIL's Unsafe-Act/Unsafe-Condition and Near-Miss Reports.”*

To ensure complete fairness, safety, and demonstrability without endangering or altering historical enterprise records, Admin Flow provides a **self-contained demonstration sandbox**. It boots with genuine **zero baseline counters** and allows live observation submissions and dataset uploads in total isolation from the existing enterprise database.

---

## 2. Non-Negotiable Isolation Rules

1. **Zero Enterprise Contamination**: Admin Flow actions (observation submission, dataset ingestion, classifications) NEVER affect existing enterprise counts, dashboards, or database rows.
2. **Zero Ingestion Leakage**: Historical enterprise incidents (561,000+ records) NEVER appear in Admin Flow.
3. **Genuine Computed Baseline**: Admin Flow starts with `0` incidents, `0` predictions, and `0` reviews. Zeros are computed live from the isolated database scope, never hardcoded as static template text.
4. **Existing User Invariance**: Standard users (`admin`, `safety_officer`, `analyst`, `viewer`) see zero changes to their UI, navbar, dashboards, or data.

---

## 3. Architecture & Data Model Scoping

### Role Architecture
- Extended Django `User.Role` with `ADMIN_FLOW = "admin_flow", "Admin Flow"`.
- Added `User.is_admin_flow` property.
- Configured dedicated demo user `admin_flow@foresight.app` (Password: `foresight2026`, Role: `admin_flow`).
- `LoginView.get_success_url()` automatically redirects `admin_flow` users to `/admin-flow/dashboard/`.

### Persistent Scoping Mechanism
Rather than duplicating database tables, persistent hard isolation is achieved through indexed nullable column scoping on core entities:
```python
# apps/incidents/models.py & apps/datasets/models.py
workspace_id = models.CharField(
    max_length=50,
    null=True,
    blank=True,
    default=None,
    db_index=True,
    help_text="Workspace isolation identifier. NULL indicates standard global enterprise data; 'admin_flow' denotes isolated judge demo workspace."
)
```

- `workspace_id IS NULL` &rarr; Enterprise Production Scope (561,000+ historical records).
- `workspace_id = 'admin_flow'` &rarr; Admin Flow Demonstration Scope.

All existing historical database rows retain `workspace_id IS NULL`. No migrations touch historical data or alter production semantics.

---

## 4. Canonical Data Access Contract

All data access is centralized in [`apps/admin_flow/services.py`](file:///Users/sas/Developer/prototype_165/apps/admin_flow/services.py). Raw `if user.is_admin_flow` logic is NOT scattered throughout the codebase.

```python
ADMIN_FLOW_WORKSPACE = "admin_flow"

def is_admin_flow_user(user) -> bool:
    """Returns True if the authenticated user has the admin_flow role."""
    return getattr(user, "is_authenticated", False) and getattr(user, "is_admin_flow", False)

def get_admin_flow_workspace(request_or_user) -> str:
    """Returns the workspace string for the user context."""
    return ADMIN_FLOW_WORKSPACE

def get_admin_flow_incidents(queryset=None):
    """Returns queryset scoped strictly to workspace_id='admin_flow'."""
    qs = queryset if queryset is not None else Incident.objects.all()
    return qs.filter(workspace_id=ADMIN_FLOW_WORKSPACE)

def get_global_incidents(queryset=None):
    """Returns enterprise production incidents (workspace_id IS NULL)."""
    qs = queryset if queryset is not None else Incident.objects.all()
    return qs.filter(workspace_id__isnull=True)

def get_admin_flow_analytics_summary() -> Dict[str, Any]:
    """
    Computes genuine analytics metrics over Admin Flow incidents only.
    Initial state evaluates to true zeros:
      Total Incidents = 0
      Prediction Eligible = 0
      PSIF Candidates = 0
      Not PSIF = 0
      Insufficient Evidence = 0
      Human Reviewed = 0
    """
```

In the standard enterprise analytics pipeline ([`apps/dashboard/services.py`](file:///Users/sas/Developer/prototype_165/apps/dashboard/services.py)), queries filter by `workspace_id__isnull=True`, guaranteeing that adding demonstration incidents never alters enterprise KPIs.

---

## 5. Dedicated URL Namespace & Routing

All Admin Flow functionality is contained within the `/admin-flow/` URL namespace:

| URL Pattern | View | Description |
|---|---|---|
| `/admin-flow/dashboard/` | `AdminFlowDashboardView` | Real-time computed KPIs and demo hero overview |
| `/admin-flow/submit/` | `AdminFlowSubmitReportView` | Incident observation entry stamped with `workspace_id='admin_flow'` |
| `/admin-flow/upload/` | `AdminFlowUploadDatasetView` | Dataset batch upload scoped to `admin_flow` |
| `/admin-flow/incidents/` | `AdminFlowIncidentListView` | Incident list filtered strictly to `workspace_id='admin_flow'` |
| `/admin-flow/incidents/<pk>/` | `AdminFlowIncidentDetailView` | Incident detail (returns 404 for global incidents) |
| `/admin-flow/psif/` | `AdminFlowPSIFClassificationView` | Precursor detection workbench (PSIF candidates vs non-PSIF) |
| `/admin-flow/iogp/` | `AdminFlowIOGPClassificationView` | IOGP Life-Saving Rules matching breakdown |
| `/admin-flow/patterns/` | `AdminFlowPatternAnalysisView` | Foundation route for pattern clustering and temporal analysis |
| `/admin-flow/api/analytics/overview/` | `AdminFlowAnalyticsOverviewAPI` | Scoped REST API for Admin Flow live metrics |

---

## 6. Access Control & Security Invariants

1. **Server-Side Enforcement**: Client requests cannot bypass scoping by supplying `?workspace_id=...` or altering JSON request bodies. Scoping is derived entirely on the server via authenticated user credentials.
2. **Standard User Denial**: Standard enterprise users accessing any `/admin-flow/*` URL receive HTTP `403 Forbidden`.
3. **Anonymous Redirection**: Unauthenticated visitors are redirected to `/accounts/login/`.
4. **Object-Level Traversal Prevention**: Attempting to view a global production incident through `/admin-flow/incidents/<global_id>/` returns HTTP `404 Not Found`.
5. **API Permission Classes**: REST endpoints enforce `IsAdminFlowUser` permission class.

---

## 7. Vertical Navbar Contract

When an `admin_flow` user logs in, the vertical sidebar displays **exclusively** the 7 required menu items:

1. **Dashboard** (`/admin-flow/dashboard/`)
2. **Submit Report** (`/admin-flow/submit/`)
3. **Upload dataset** (`/admin-flow/upload/`)
4. **Incidents** (`/admin-flow/incidents/`)
5. **PSIF Classification** (`/admin-flow/psif/`)
6. **IOGP classification** (`/admin-flow/iogp/`)
7. **Pattern Analysis** (`/admin-flow/patterns/`)

Standard enterprise users retain their full original navigation (Dashboard, Datasets, Incidents, Investigation, Adjudication, Data Quality, Benchmarks, Retrain) with zero visual alterations.

---

## 8. Regression Guarantees

- **Migration Safety**: Zero schema breakages. `workspace_id` added as a nullable, indexed field with default `None`.
- **Performance**: Index on `workspace_id` ensures $O(\log N)$ or fast index scans for both enterprise (`IS NULL`) and Admin Flow (`= 'admin_flow'`) filters.
- **Automated Verification**: Full automated test coverage in `tests/test_admin_flow_isolation.py` guaranteeing two-way isolation, access control, and navbar invariants.
