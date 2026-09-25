"""
PSIF Platform — Tests for Normalized Cross-Site Intelligence
tests/test_cross_site_intelligence.py

Comprehensive test suite covering:
1. Deterministic site normalization & adversarial tests ("Duliajan Workshop" must not merge into "DULIAJAN")
2. Unknown site preservation
3. Activity normalization (driving vs servicing vs permit vs lifting)
4. Hazard normalization (preserving distinction: equipment vs energy vs exposure)
5. IOGP Life-Saving Rules as "RULE-DERIVED CANDIDATE"
6. Normalization traceability & status codes (no fake confidence percentages)
7. Cross-site aggregations & explicit denominators
8. Distinct site counting & multi-site recurrence patterns
9. Neutral analytical phrasing (never "Site X is unsafe")
10. REST API endpoints (authenticated 200, unauthenticated 403, 404 handling, query params)
11. Template view rendering
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from rest_framework import status
from rest_framework.test import APIClient

from apps.incidents.models import Incident, IOGPRuleTag
from apps.incidents.services.normalization import (
    NORMALIZATION_VERSION,
    NormalizationStatus,
    NormalizationMethod,
    NormalizedEntity,
    CANONICAL_OPERATIONAL_SITES,
    CANONICAL_ACTIVITIES,
    CANONICAL_HAZARDS,
    CANONICAL_IOGP_RULES,
    normalize_site,
    normalize_operational_site,
    normalize_activity,
    normalize_hazard,
    normalize_equipment,
    normalize_iogp_rule,
    resolve_operational_site,
)
from apps.dashboard.cross_site_service import (
    METHODOLOGY_DISCLOSURE,
    PLATFORM_LIMITATIONS,
    get_cross_site_overview,
    get_site_comparison_table,
    get_site_detail,
    get_site_iogp_matrix,
    get_site_hazard_matrix,
    get_normalized_activities_cross_site,
    get_normalized_hazards_cross_site,
    get_normalized_iogp_cross_site,
    compare_sites,
    get_cross_site_recurrence_signals,
)
from apps.predictions.models import PredictionResult


# ── Fixture: Multi-Site Incidents Dataset ──────────────────────────────────────

@pytest.fixture
def multi_site_data(db):
    """Creates a controlled cross-site dataset across Duliajan, Numaligarh, and Moran."""
    from apps.predictions.models import ModelVersion
    mv = ModelVersion.objects.create(
        version_label="test_v1",
        is_active=True,
        bert_model_name="distilbert-base-uncased",
    )

    # 1. Incident at Duliajan
    inc1 = Incident.objects.create(
        description="Forklift operating near pipe rack in Duliajan",
        composite_narrative="Forklift operating near pipe rack in Duliajan",
        job_task="driving",
        energy_type="motor_vehicle",
        raw_row={"region_field": "Duliajan Site", "energy_source": "Kinetic (vehicle)"},
    )
    PredictionResult.objects.create(incident=inc1, model_version=mv, psif_predicted=True, psif_probability=0.82)
    IOGPRuleTag.objects.create(incident=inc1, rule="Driving", matched_keywords=["forklift"])

    # 2. Second Incident at Duliajan
    inc2 = Incident.objects.create(
        description="Rigging sling inspection before lifting load at Duliajan",
        composite_narrative="Rigging sling inspection before lifting load at Duliajan",
        job_task="lifting operation",
        energy_type="gravity",
        raw_row={"region_field": "DULIAJAN", "energy_source": "Gravity"},
    )
    PredictionResult.objects.create(incident=inc2, model_version=mv, psif_predicted=False, psif_probability=0.15)
    IOGPRuleTag.objects.create(incident=inc2, rule="Safe Mechanical Lifting", matched_keywords=["lifting"])

    # 3. Incident at Numaligarh
    inc3 = Incident.objects.create(
        description="Speeding tanker truck on internal refinery road in Numaligarh",
        composite_narrative="Speeding tanker truck on internal refinery road in Numaligarh",
        job_task="driving",
        energy_type="motor_vehicle",
        raw_row={"region_field": "Numaligarh Refinery", "energy_source": "Kinetic (vehicle)"},
    )
    PredictionResult.objects.create(incident=inc3, model_version=mv, psif_predicted=True, psif_probability=0.74)
    IOGPRuleTag.objects.create(incident=inc3, rule="Driving", matched_keywords=["speeding truck"])

    # 4. Incident at Moran
    inc4 = Incident.objects.create(
        description="Maintenance crew servicing fleet truck brake lines at Moran",
        composite_narrative="Maintenance crew servicing fleet truck brake lines at Moran",
        job_task="vehicle maintenance",
        energy_type="pressure",
        raw_row={"region_field": "GGS Moran", "energy_source": "Pressure"},
    )
    PredictionResult.objects.create(incident=inc4, model_version=mv, psif_predicted=False, psif_probability=0.18)
    IOGPRuleTag.objects.create(incident=inc4, rule="Energy Isolation", matched_keywords=["servicing"])

    return {
        "incidents": [inc1, inc2, inc3, inc4],
        "sites": ["DULIAJAN", "NUMALIGARH", "MORAN"],
    }


# ── 1. Site Normalization & Adversarial Tests ─────────────────────────────────

class TestSiteNormalization:
    """Tests deterministic site normalization and unknown preservation."""

    def test_canonical_site_exact_match(self):
        ent = normalize_operational_site("DULIAJAN")
        assert ent.canonical_value == "DULIAJAN"
        assert ent.is_exact
        assert ent.status_code == "EXACT"
        assert ent.method in (NormalizationMethod.EXACT, NormalizationMethod.NORMALIZED)

    def test_site_casing_and_whitespace_normalization(self):
        for raw in ["duliajan", "Duliajan", "  DULIAJAN  ", "duliajan "]:
            ent = normalize_operational_site(raw)
            assert ent.canonical_value == "DULIAJAN", f"Failed for raw={raw!r}"
            assert ent.is_normalized

    def test_site_common_aliases(self):
        for raw in ["duliajan site", "duliajan-site", "site duliajan", "central tank farm duliajan", "ctf duliajan"]:
            ent = normalize_operational_site(raw)
            assert ent.canonical_value == "DULIAJAN", f"Failed for raw={raw!r}"
            assert ent.is_alias or ent.is_normalized

    def test_numaligarh_refinery_aliases(self):
        for raw in ["numaligarh", "numaligarh refinery", "numaligarh site", "numaligarh refinery - tank farm"]:
            ent = normalize_operational_site(raw)
            assert ent.canonical_value == "NUMALIGARH", f"Failed for raw={raw!r}"

    def test_moran_and_naharkatiya_aliases(self):
        assert normalize_operational_site("moran").canonical_value == "MORAN"
        assert normalize_operational_site("ggs moran").canonical_value == "MORAN"
        assert normalize_operational_site("naharkatiya").canonical_value == "NAHARKATIYA"
        assert normalize_operational_site("nhk").canonical_value == "NAHARKATIYA"

    def test_adversarial_distinct_facility_must_not_merge(self):
        """
        Adversarial test: 'Duliajan Workshop' must NOT automatically merge into
        canonical 'DULIAJAN' because it is a distinct maintenance workshop/functional facility,
        not the general field installation.
        """
        ent = normalize_operational_site("Duliajan Workshop")
        assert ent.canonical_value != "DULIAJAN", (
            f"Adversarial failure: 'Duliajan Workshop' was incorrectly collapsed to '{ent.canonical_value}'"
        )
        assert ent.status_code in ("UNKNOWN", "UNCERTAIN")

    def test_adversarial_distinct_rig_must_not_merge(self):
        """
        Rig 9 and Rig 14 must remain distinct entities and not collapse together.
        """
        r9 = normalize_operational_site("Drilling Rig 9")
        r14 = normalize_operational_site("Drilling Rig 14")
        assert r9.canonical_value != r14.canonical_value
        assert "9" in r9.canonical_value
        assert "14" in r14.canonical_value

    def test_unknown_site_preservation(self):
        for raw in ["", None, "   ", "unknown", "n/a", "na", "unspecified", "generic area"]:
            ent = normalize_operational_site(raw)
            assert ent.canonical_value == "UNKNOWN", f"Failed for raw={raw!r}"
            assert ent.status_code == "UNKNOWN"
            assert not ent.is_exact
            assert not ent.is_alias


# ── 2. Activity Normalization Tests ───────────────────────────────────────────

class TestActivityNormalization:
    """Tests deterministic activity normalization and boundary distinctions."""

    def test_safe_mechanical_lifting_normalization(self):
        for raw in ["lifting operation", "material lifting", "lifting materials", "safe mechanical lifting", "rigging"]:
            ent = normalize_activity(raw)
            assert ent.canonical_value in ("Safe Mechanical Lifting", "Lifting Operations / Rigging"), f"Failed for raw={raw!r}"
            assert ent.is_normalized

    def test_distinguish_driving_vs_vehicle_maintenance(self):
        driving_ent = normalize_activity("driving")
        maint_ent = normalize_activity("vehicle maintenance")

        assert driving_ent.canonical_value == "Vehicle Operation / Road Transport"
        assert maint_ent.canonical_value == "Vehicle Maintenance / Servicing"
        assert driving_ent.canonical_value != maint_ent.canonical_value

    def test_distinguish_permit_authorization_vs_routine_work(self):
        for raw in ["permit to work", "work permit", "ptw", "work authorization"]:
            ent = normalize_activity(raw)
            assert ent.canonical_value == "Permit to Work / Work Authorization"

    def test_distinguish_confined_space_vs_hot_work(self):
        cs_ent = normalize_activity("tank cleaning")
        hw_ent = normalize_activity("hot work")

        assert cs_ent.canonical_value == "Internal Pressure Vessel Cleaning"
        assert hw_ent.canonical_value in ("Hot Work / Welding / Cutting", "Hot Work in Classified Area")
        assert cs_ent.canonical_value != hw_ent.canonical_value


# ── 3. Hazard Normalization & Distinction Tests ───────────────────────────────

class TestHazardNormalization:
    """Tests 15 canonical hazard families and distinction between equipment and energy."""

    def test_equipment_is_not_hazard_release(self):
        """
        'Pressure vessel' is equipment, not an active pressure release hazard.
        Equipment normalizes to 'Pressure Vessel', while hazard normalizes to
        'Pressure / Stored Energy Release'.
        """
        eq_ent = normalize_equipment("pressure vessel")
        assert eq_ent.canonical_value == "Pressure Vessel"

        hz_ent = normalize_hazard("pressure release")
        assert hz_ent.canonical_value == "Pressure / Stored Energy Release"
        assert eq_ent.canonical_value != hz_ent.canonical_value

    def test_real_incident_energy_sources_mapped_to_canonical_hazards(self):
        mappings = {
            "Kinetic (vehicle)": "Vehicle & Mobile Equipment",
            "Kinetic (moving object/vehicle)": "Vehicle & Mobile Equipment",
            "Gravity": "Working at Height",
            "Gravity (dropped object)": "Dropped Objects (Dynamic Gravity Impact)",
            "Mechanical": "Rotating Equipment / Mechanical In-Running Nips",
            "Mechanical (rotating equipment)": "Rotating Equipment / Mechanical In-Running Nips",
            "Hydrocarbon (flammable atmosphere)": "Hydrocarbon & Flammable Chemical Release",
            "Hydrocarbon": "Hydrocarbon & Flammable Chemical Release",
            "Pressure": "Pressure / Stored Energy Release",
            "Electrical": "Electrical Energy / Arc Flash",
            "Chemical (toxic/H2S)": "Toxic & Asphyxiant Atmosphere",
            "Atmospheric (oxygen deficiency)": "Confined Space / Engulfment",
            "Thermal": "Thermal Energy (Extreme Heat / Cryogenic)",
        }
        for raw, expected in mappings.items():
            ent = normalize_hazard(raw)
            assert ent.canonical_value == expected, f"Failed for raw={raw!r}: got {ent.canonical_value!r}"


# ── 4. IOGP Life-Saving Rules Normalization Tests ─────────────────────────────

class TestIOGPNormalization:
    """Tests 9 canonical IOGP rules and candidate labeling."""

    def test_all_9_canonical_rules_present(self):
        assert len(CANONICAL_IOGP_RULES) == 9
        expected = {
            "Bypassing Safety Controls",
            "Confined Space",
            "Driving",
            "Energy Isolation",
            "Hot Work",
            "Line of Fire",
            "Safe Mechanical Lifting",
            "Work Authorization",
            "Working at Height",
        }
        assert set(CANONICAL_IOGP_RULES) == expected

    def test_iogp_rule_normalization_aliases(self):
        assert normalize_iogp_rule("bypassing controls").canonical_value == "Bypassing Safety Controls"
        assert normalize_iogp_rule("safe driving").canonical_value == "Driving"
        assert normalize_iogp_rule("loto").canonical_value == "Energy Isolation"
        assert normalize_iogp_rule("line-of-fire").canonical_value == "Line of Fire"
        assert normalize_iogp_rule("lifting").canonical_value == "Safe Mechanical Lifting"
        assert normalize_iogp_rule("ptw").canonical_value == "Work Authorization"
        assert normalize_iogp_rule("work at height").canonical_value == "Working at Height"


# ── 5. Traceability & No Fake Confidence Tests ────────────────────────────────

class TestNormalizationTraceability:
    """Tests full traceability metadata without fake probabilistic confidence percentages."""

    def test_traceability_fields_preserved(self):
        ent = normalize_operational_site("duliajan site", source_field="raw_row.region_field")
        d = ent.to_dict()

        assert d["raw_value"] == "duliajan site"
        assert d["canonical_value"] == "DULIAJAN"
        assert d["status_code"] in ("ALIAS", "EXACT", "NORMALIZED")
        assert d["source_field"] == "raw_row.region_field"
        assert d["version"] == NORMALIZATION_VERSION

    def test_unknown_traceability(self):
        ent = normalize_operational_site("", source_field="raw_row.region_field")
        d = ent.to_dict()
        assert d["canonical_value"] == "UNKNOWN"
        assert d["status_code"] == "UNKNOWN"
        assert d["method"] == "unknown"


# ── 6. Cross-Site Service & Aggregation Tests ─────────────────────────────────

@pytest.mark.django_db
class TestCrossSiteAnalyticsService:
    """Tests cross-site aggregation engine, explicit denominators, and performance."""

    def test_overview_empty_dataset_graceful_handling(self):
        overview = get_cross_site_overview(force_refresh=True)
        assert overview["total_observations"] == 0
        assert overview["psif_rate_pct"] == 0.0
        assert "methodology_notice" in overview
        assert "limitations" in overview

    def test_overview_with_data(self, multi_site_data):
        overview = get_cross_site_overview(force_refresh=True)
        assert overview["total_observations"] == 4
        assert overview["prediction_eligible_count"] == 4
        assert overview["total_psif_candidate_count"] == 2
        assert overview["psif_rate_pct"] == 50.0
        assert overview["distinct_operational_sites_count"] == 3
        assert "DULIAJAN" in overview["active_operational_sites"]
        assert "NUMALIGARH" in overview["active_operational_sites"]

    def test_site_comparison_table_neutral_wording_and_denominators(self, multi_site_data):
        table = get_site_comparison_table(force_refresh=True)
        assert len(table) > 0

        for row in table:
            assert "site_name" in row
            assert "total_observations" in row
            assert "prediction_eligible_observations" in row
            assert "psif_candidate_count" in row
            assert "psif_rate_pct" in row
            assert "neutral_volume_label" in row
            assert "Observed safety-signal volume" in row["neutral_volume_label"]
            assert "unsafe" not in row["neutral_volume_label"].lower()
            assert "denominator" in row
            assert "n = " in row["denominator"]

    def test_site_detail_for_duliajan(self, multi_site_data):
        detail = get_site_detail("DULIAJAN", force_refresh=True)
        assert detail is not None
        assert detail["canonical_site"] == "DULIAJAN"
        assert detail["total_observations"] == 2
        assert detail["psif_candidate_count"] == 1
        assert detail["psif_rate_pct"] == 50.0
        assert "departments" in detail
        assert "iogp_rule_candidates" in detail
        assert "top_activities" in detail
        assert "top_hazards" in detail

        for rule in detail["iogp_rule_candidates"]:
            assert rule["status"] == "RULE-DERIVED CANDIDATE"

    def test_site_iogp_matrix_structure(self, multi_site_data):
        matrix = get_site_iogp_matrix(force_refresh=True)
        assert "rules" in matrix
        assert len(matrix["rules"]) == 9
        assert "sites" in matrix
        assert "rows" in matrix
        assert len(matrix["rows"]) == 3  # Duliajan, Numaligarh, Moran

        for row in matrix["rows"]:
            assert "site" in row
            assert "total" in row
            for r in CANONICAL_IOGP_RULES:
                assert r in row

    def test_site_hazard_matrix_structure(self, multi_site_data):
        matrix = get_site_hazard_matrix(force_refresh=True)
        assert "hazards" in matrix
        assert len(matrix["hazards"]) == 15
        assert "sites" in matrix
        assert "rows" in matrix
        assert len(matrix["rows"]) == 3

        for row in matrix["rows"]:
            assert "site" in row
            assert "total" in row

    def test_normalized_activities_cross_site(self, multi_site_data):
        acts = get_normalized_activities_cross_site(force_refresh=True)
        assert len(acts) > 0
        for a in acts:
            assert "canonical_activity" in a
            assert "total_observations" in a
            assert "distinct_sites_count" in a
            assert "denominator" in a
            assert "n = " in a["denominator"]

    def test_normalized_hazards_cross_site(self, multi_site_data):
        hzs = get_normalized_hazards_cross_site(force_refresh=True)
        assert len(hzs) == 15
        for h in hzs:
            assert "canonical_hazard" in h
            assert "total_observations" in h
            assert "distinct_sites_count" in h
            assert "denominator" in h

    def test_normalized_iogp_cross_site_disclaimer(self, multi_site_data):
        rules = get_normalized_iogp_cross_site(force_refresh=True)
        assert len(rules) == 9
        for r in rules:
            assert "RULE-DERIVED CANDIDATE" in r["status_disclaimer"]
            assert "n = " in r["denominator"]

    def test_compare_sites_head_to_head(self, multi_site_data):
        cmp = compare_sites(["DULIAJAN", "NUMALIGARH"])
        assert cmp["site_count"] == 2
        assert "compared_sites" in cmp
        assert "DULIAJAN" in cmp["compared_sites"]
        assert "NUMALIGARH" in cmp["compared_sites"]
        assert "shared_iogp_rules" in cmp
        assert "Driving" in cmp["shared_iogp_rules"]
        assert "shared_activities" in cmp
        assert "Vehicle Operation / Road Transport" in cmp["shared_activities"]
        assert cmp["methodology_notice"] == METHODOLOGY_DISCLOSURE

    def test_cross_site_recurrence_non_causal_statement(self, multi_site_data):
        signals = get_cross_site_recurrence_signals()
        assert len(signals) > 0
        for sig in signals:
            assert sig["rule_status"] == "RULE-DERIVED CANDIDATE"
            assert sig["guidance_statement"] == "Similar observations have been recorded across multiple sites."
            assert "cause" not in sig["guidance_statement"].lower()
            assert "predict" not in sig["guidance_statement"].lower()
            assert sig["site_count"] >= 2


# ── 7. REST API Endpoints Tests ───────────────────────────────────────────────

@pytest.mark.django_db
class TestCrossSiteRESTAPIs:
    """Tests all 8 REST API endpoints for authentication, status, schema, and errors."""

    @pytest.fixture(autouse=True)
    def setup_user(self):
        User = get_user_model()
        self.user = User.objects.first()
        if not self.user:
            self.user = User.objects.create_user(username="api_tester", password="password123")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.anon_client = APIClient()

    def test_unauthenticated_requests_forbidden(self):
        res = self.anon_client.get("/api/cross-site/overview/")
        assert res.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_api_overview_200(self, multi_site_data):
        res = self.client.get("/api/cross-site/overview/?refresh=true")
        assert res.status_code == status.HTTP_200_OK
        data = res.data
        assert "total_observations" in data
        assert "denominators" in data
        assert data["methodology_notice"] == METHODOLOGY_DISCLOSURE

    def test_api_sites_200(self, multi_site_data):
        res = self.client.get("/api/cross-site/sites/?refresh=true")
        assert res.status_code == status.HTTP_200_OK
        data = res.data
        assert "count" in data
        assert "sites" in data
        assert "metadata" in data
        assert data["count"] > 0

    def test_api_site_detail_valid_and_invalid(self, multi_site_data):
        res = self.client.get("/api/cross-site/sites/DULIAJAN/?refresh=true")
        assert res.status_code == status.HTTP_200_OK
        assert res.data["site"]["canonical_site"] == "DULIAJAN"

        # Invalid site returns 404 with normalized attempt
        res_404 = self.client.get("/api/cross-site/sites/NONEXISTENT_SITE_XYZ/")
        assert res_404.status_code == status.HTTP_404_NOT_FOUND
        assert "normalized_attempt" in res_404.data

    def test_api_activities_200(self, multi_site_data):
        res = self.client.get("/api/cross-site/activities/?refresh=true")
        assert res.status_code == status.HTTP_200_OK
        assert "activities" in res.data
        assert len(res.data["activities"]) > 0

    def test_api_hazards_200(self, multi_site_data):
        res = self.client.get("/api/cross-site/hazards/?refresh=true")
        assert res.status_code == status.HTTP_200_OK
        assert "hazards" in res.data
        assert len(res.data["hazards"]) == 15

    def test_api_iogp_200(self, multi_site_data):
        res = self.client.get("/api/cross-site/iogp/?refresh=true")
        assert res.status_code == status.HTTP_200_OK
        assert "rules" in res.data
        assert len(res.data["rules"]) == 9
        assert "site_matrix" in res.data

    def test_api_compare_200(self, multi_site_data):
        res = self.client.get("/api/cross-site/compare/?sites=DULIAJAN,NUMALIGARH")
        assert res.status_code == status.HTTP_200_OK
        assert "comparison" in res.data
        assert res.data["comparison"]["site_count"] == 2

    def test_api_recurrence_200(self, multi_site_data):
        res = self.client.get("/api/cross-site/recurrence/?min_sites=2")
        assert res.status_code == status.HTTP_200_OK
        assert "recurrence_signals" in res.data
        for sig in res.data["recurrence_signals"]:
            assert sig["site_count"] >= 2


# ── 8. HTML UI Rendering Tests ────────────────────────────────────────────────

@pytest.mark.django_db
class TestCrossSiteUIRendering:
    """Tests the /dashboard/cross-site/ HTML view rendering and contents."""

    @pytest.fixture(autouse=True)
    def setup_user(self):
        User = get_user_model()
        self.user = User.objects.first()
        if not self.user:
            self.user = User.objects.create_user(username="ui_tester", password="password123")
        self.client = Client()
        self.client.force_login(self.user)

    def test_cross_site_page_loads_200(self, multi_site_data):
        res = self.client.get("/dashboard/cross-site/")
        assert res.status_code == 200
        content = res.content.decode("utf-8")

        assert "Cross-Site Safety Signal Intelligence" in content
        assert "DULIAJAN" in content
        assert "NUMALIGARH" in content
        assert "Methodology Disclosure" in content
        assert "Prototype Architecture" in content
        assert "RULE-DERIVED CANDIDATE" in content
        assert "Similar observations have been recorded across multiple sites." in content
        assert "Observed Safety-Signal Volume" in content

    def test_anonymous_redirected_to_login(self):
        anon_client = Client()
        res = anon_client.get("/dashboard/cross-site/")
        assert res.status_code == 302
        assert "/login" in res.url
