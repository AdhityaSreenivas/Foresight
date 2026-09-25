"""
PSIF Platform — Tests for Safety Entity Normalization, Canonical Terminology,
Methodology Disclosures, and Analytical Evidence Structures.
"""

import pytest
from django.template import Template, Context
from django.urls import reverse
from rest_framework.test import APIClient

from apps.incidents.models import Incident, IOGPRuleTag
from apps.incidents.serializers import IncidentDetailSerializer
from apps.incidents.services.normalization import (
    NormalizationMethod,
    NormalizationStatus,
    NormalizedEntity,
    normalize_entity,
    normalize_location,
    normalize_site,
    normalize_department,
    normalize_activity,
    normalize_job_task,
    normalize_equipment,
    normalize_energy_source,
    normalize_control_type,
    normalize_control_condition,
    normalize_iogp_rule,
    normalize_incident_entities,
    CANONICAL_LOCATIONS,
    CANONICAL_DEPARTMENTS,
    CANONICAL_ACTIVITIES,
    CANONICAL_EQUIPMENT_CLASSES,
    CANONICAL_ENERGY_SOURCES,
    CANONICAL_CONTROL_TYPES,
    CANONICAL_CONTROL_CONDITIONS,
    CANONICAL_IOGP_RULES,
)
from apps.incidents.services.methodology import (
    MethodologyKey,
    get_methodology_notice,
    get_all_methodology_notices,
    METHODOLOGY_NOTICES,
)
from apps.incidents.services.evidence import (
    AnalyticalEvidence,
    EvidenceSource,
    EvidenceType,
    EvidenceStrength,
    evidence_from_shap,
    evidence_from_incident_field,
    evidence_from_iogp_tag,
    evidence_from_similar_incident,
    evidence_from_recurrence_pattern,
    evidence_from_control_status,
    evidence_from_data_quality,
)
from apps.incidents.services.decision_trace import build_analytical_assessment
from apps.dashboard.pattern_detection import detect_recurring_patterns, detect_multi_site_recurrence


# ── 1. Normalization Determinism & Syntax Sanitation ──────────────────────────

@pytest.mark.django_db
class TestNormalizationDeterminism:
    def test_normalization_is_deterministic(self):
        """Repeated calls with identical inputs must return identical results."""
        res1 = normalize_department("Drilling Operations")
        res2 = normalize_department("Drilling Operations")
        assert res1 == res2
        assert res1.canonical_value == "Drilling"
        assert res1.status == NormalizationStatus.RESOLVED

    def test_case_and_whitespace_insensitivity(self):
        """Variations in case and whitespace must map to identical canonical entity."""
        variants = [
            "  tank farm  ",
            "TANK FARM",
            "tank   farm",
            "Tank Farm\n",
        ]
        for v in variants:
            res = normalize_location(v)
            assert res.canonical_value == "Tank Farm"
            assert res.status in (NormalizationStatus.CANONICAL, NormalizationStatus.RESOLVED)
            assert res.raw_value == v

    def test_punctuation_normalization(self):
        """Punctuation differences like slashes or hyphens resolve cleanly."""
        res_slash = normalize_location("Workshop/Maintenance Bay")
        res_space = normalize_location("Workshop Maintenance Bay")
        assert res_slash.canonical_value == "Workshop/Maintenance Bay"
        assert res_space.canonical_value == "Workshop/Maintenance Bay"


# ── 2. Alias Handling Across All Safety Entity Types ──────────────────────────

@pytest.mark.django_db
class TestAliasHandling:
    def test_site_location_aliases(self):
        cases = [
            ("jetty", "Jetty/Marine Terminal"),
            ("marine terminal", "Jetty/Marine Terminal"),
            ("tankfarm", "Tank Farm"),
            ("rig floor", "Drill Floor"),
            ("whp", "Wellhead Platform"),
            ("comp station", "Compressor Station"),
            ("maint bay", "Workshop/Maintenance Bay"),
            ("pipeline row", "Pipeline ROW"),
            ("pwt", "Produced Water Treatment"),
        ]
        for raw, expected in cases:
            res = normalize_location(raw)
            assert res.canonical_value == expected, f"Failed for raw='{raw}'"
            assert res.method in (NormalizationMethod.EXACT_ALIAS, NormalizationMethod.EXACT_CANONICAL, NormalizationMethod.NORMALIZED_SYNTAX)
            assert res.status in (NormalizationStatus.RESOLVED, NormalizationStatus.CANONICAL)

    def test_department_aliases(self):
        cases = [
            ("drill ops", "Drilling"),
            ("well intervention", "Workover"),
            ("refinery ops", "Refinery Operations"),
            ("mech maint", "Mechanical Maintenance"),
            ("elec maint", "Electrical Maintenance"),
            ("i&c", "Instrumentation"),
            ("stores", "Logistics & Stores"),
            ("ehs", "HSE / Safety"),
            ("operations", "Production Operations"),
        ]
        for raw, expected in cases:
            res = normalize_department(raw)
            assert res.canonical_value == expected, f"Failed for raw='{raw}'"
            assert res.status in (NormalizationStatus.RESOLVED, NormalizationStatus.CANONICAL)

    def test_activity_job_task_aliases(self):
        cases = [
            ("hot work in a hydrocarbon-classified area", "Hot Work in Classified Area"),
            ("vessel entry", "Confined Space Vessel Entry"),
            ("work on a floating or fixed tank roof", "Work at Height / Scaffold Work"),
            ("marine hydrocarbon transfer at the jetty", "Marine Hydrocarbon Transfer"),
            ("pipeline tie-in / hot tap operation", "Pipeline Tie-In / Hot Tap"),
            ("internal cleaning of a pressure vessel", "Internal Pressure Vessel Cleaning"),
            ("lockout tagout", "Energy Isolation / LOTO"),
        ]
        for raw, expected in cases:
            res = normalize_activity(raw)
            assert res.canonical_value == expected, f"Failed for raw='{raw}'"
            assert res.status == NormalizationStatus.RESOLVED

    def test_equipment_asset_aliases_and_tag_extraction(self):
        """Equipment normalization identifies asset class and preserves asset tag in metadata."""
        cases = [
            ("Chemical Pump CP-12", "Chemical Pump", "CP-12"),
            ("Hydraulic Press HP-100", "Hydraulic Press", "HP-100"),
            ("Electrical Panel EP-7", "Electrical Panel", "EP-7"),
            ("Portable Generator PG-5", "Portable Generator", "PG-5"),
            ("Boom Lift BL-40", "Boom Lift / MEWP", "BL-40"),
            ("Angle Grinder", "Angle Grinder", None),
        ]
        for raw, expected_class, expected_tag in cases:
            res = normalize_equipment(raw)
            assert res.canonical_value == expected_class, f"Failed for raw='{raw}'"
            if expected_tag:
                assert res.metadata.get("asset_tag") == expected_tag

    def test_energy_source_aliases(self):
        cases = [
            ("gravity_height", "Gravity / Working at Height"),
            ("high voltage", "Electrical"),
            ("rotating equipment", "Mechanical Motion / Rotating Equipment"),
            ("high pressure", "Pressure / Stored Energy"),
            ("hydrocarbon", "Chemical / Toxic / Flammable"),
            ("hot surface", "Thermal (Extreme Heat/Cold)"),
        ]
        for raw, expected in cases:
            res = normalize_energy_source(raw)
            assert res.canonical_value == expected

    def test_barrier_control_aliases(self):
        # Control type
        res_loto = normalize_control_type("loto_isolation")
        assert res_loto.canonical_value == "LOTO / Energy Isolation (Direct)"
        res_guard = normalize_control_type("guarding")
        assert res_guard.canonical_value == "Machine Guarding / Interlocks (Direct)"

        # Control condition
        res_held = normalize_control_condition("held")
        assert res_held.canonical_value == "Effective / Held"
        res_fail = normalize_control_condition("malfunctioned")
        assert res_fail.canonical_value == "Failed"
        res_bypass = normalize_control_condition("overridden")
        assert res_bypass.canonical_value == "Bypassed / Defeated"

    def test_iogp_rule_aliases(self):
        cases = [
            ("bypass controls", "Bypassing Safety Controls"),
            ("confined spaces", "Confined Space"),
            ("safe driving", "Driving"),
            ("energy isolation", "Energy Isolation"),
            ("hotwork", "Hot Work"),
            ("line-of-fire", "Line of Fire"),
            ("mechanical lifting", "Safe Mechanical Lifting"),
            ("permit to work", "Work Authorization"),
            ("working at height", "Working at Height"),
        ]
        for raw, expected in cases:
            res = normalize_iogp_rule(raw)
            assert res.canonical_value == expected


# ── 3. Conservative Bounded Fuzzy Handling ────────────────────────────────────

@pytest.mark.django_db
class TestConservativeFuzzyHandling:
    def test_bounded_high_confidence_fuzzy_suggestion(self):
        """Very close typo (e.g. 'Compressor Statn') matches with bounded fuzzy."""
        res = normalize_location("Compressor Statn")
        assert res.canonical_value == "Compressor Station"
        assert res.method == NormalizationMethod.BOUNDED_FUZZY
        assert res.confidence >= 0.88
        assert res.status in (NormalizationStatus.RESOLVED, NormalizationStatus.SUGGESTED)

    def test_uncertain_strings_never_merged(self):
        """Strings below threshold must retain identity and UNCERTAIN status without being merged."""
        unrelated_strings = [
            "Cafeteria Lunch Room",
            "General Administration Building",
            "Parking Lot Gate 4",
            "Random Vendor Container",
            "Unknown Area XYZ 99",
        ]
        for raw in unrelated_strings:
            res = normalize_location(raw)
            assert res.canonical_value == raw
            assert res.method == NormalizationMethod.IDENTITY
            assert res.status == NormalizationStatus.UNCERTAIN
            assert res.confidence == 0.5


# ── 4. Raw Value Preservation & Traceability ──────────────────────────────────

@pytest.mark.django_db
class TestRawValuePreservation:
    def test_raw_values_traceable_on_normalization(self):
        raw = "   Refinery Operations Division #2   "
        res = normalize_department(raw)
        assert res.raw_value == raw
        assert res.provenance == "deterministic_taxonomy_v1"

    def test_none_and_empty_handling(self):
        for empty_val in [None, "", "   "]:
            res = normalize_department(empty_val)
            assert res.canonical_value == ""
            assert res.method == NormalizationMethod.UNMAPPED
            assert res.status == NormalizationStatus.UNMAPPED
            assert res.confidence == 0.0

    def test_incident_aggregate_normalizer(self):
        inc = Incident(
            location="loading rack",
            department="mech maint",
            job_task="welding",
            equipment_involved="Chemical Pump CP-12",
            energy_type="gravity_height",
            control_type="fall_protection",
            control_condition="failed",
        )
        entities = normalize_incident_entities(inc)
        assert set(entities.keys()) == {
            "site", "department", "activity", "equipment", "energy_source", "control_type", "control_condition"
        }
        assert entities["site"].canonical_value == "Loading Rack"
        assert entities["department"].canonical_value == "Mechanical Maintenance"
        assert entities["activity"].canonical_value == "Hot Work in Classified Area"
        assert entities["equipment"].canonical_value == "Chemical Pump"
        assert entities["equipment"].metadata.get("asset_tag") == "CP-12"
        assert entities["energy_source"].canonical_value == "Gravity / Working at Height"
        assert entities["control_type"].canonical_value == "Fall Protection / Harness / Railing (Direct)"
        assert entities["control_condition"].canonical_value == "Failed"
        # Verify raw values preserved
        assert entities["site"].raw_value == "loading rack"
        assert entities["department"].raw_value == "mech maint"
        assert entities["activity"].raw_value == "welding"


# ── 5. Methodology Disclosure System ──────────────────────────────────────────

@pytest.mark.django_db
class TestMethodologyDisclosureSystem:
    def test_all_canonical_notices_registered(self):
        expected_keys = [
            MethodologyKey.IOGP,
            MethodologyKey.SIMILARITY,
            MethodologyKey.RECURRENCE,
            MethodologyKey.PSIF_MODEL,
            MethodologyKey.SHAP,
            MethodologyKey.HUMAN_REVIEW,
            MethodologyKey.DATA_QUALITY,
            MethodologyKey.BARRIER,
        ]
        all_notices = get_all_methodology_notices()
        for k in expected_keys:
            assert k in all_notices

    def test_required_exact_methodology_strings(self):
        """Verifies exact wording mandated by safety requirements."""
        iogp_notice = get_methodology_notice("iogp")
        assert iogp_notice["summary"] == "Rule-derived candidate from deterministic keyword/phrase matching; not calibrated confidence or proof of control failure."

        sim_notice = get_methodology_notice("similarity")
        assert sim_notice["summary"] == "Semantic similarity between incident narratives; not causal evidence or duplicate identity."

        rec_notice = get_methodology_notice("recurrence")
        assert rec_notice["summary"] == "Historical recurrence based on normalized entities and time-window matching; not causal/systemic prediction."

        psif_notice = get_methodology_notice("psif_model")
        assert psif_notice["summary"] == "PSIF Model Score from the active model; score is not a calibrated probability."

        shap_notice = get_methodology_notice("shap")
        assert shap_notice["summary"] == "SHAP values show mathematical model contribution, not causality."

        human_notice = get_methodology_notice("human_review")
        assert human_notice["summary"] == "Human adjudication is shown separately from model prediction."

        dq_notice = get_methodology_notice("data_quality")
        assert dq_notice["summary"] == "Data-quality rules indicate analytical suitability; they do not establish PSIF status."

    def test_template_tags_rendering(self):
        """Template tags render valid HTML containing badge and disclosure."""
        # Full notice
        tpl1 = Template("{% load methodology_tags %}{% methodology_notice 'iogp' %}")
        rendered1 = tpl1.render(Context({}))
        assert "Rule-derived candidate from deterministic keyword" in rendered1
        assert "data-methodology-key=\"iogp\"" in rendered1

        # Compact notice
        tpl2 = Template("{% load methodology_tags %}{% methodology_notice 'psif_model' compact=True %}")
        rendered2 = tpl2.render(Context({}))
        assert "PSIF Model Score from the active model" in rendered2
        assert "methodology-notice-compact" in rendered2

        # Badge tag
        tpl3 = Template("{% load methodology_tags %}{% methodology_badge 'similarity' %}")
        rendered3 = tpl3.render(Context({}))
        assert "methodology-badge" in rendered3
        assert "Semantic Vector" in rendered3


# ── 6. Analytical Evidence Structures ─────────────────────────────────────────

@pytest.mark.django_db
class TestAnalyticalEvidenceStructures:
    def test_analytical_evidence_dataclass_serialization(self):
        ev = AnalyticalEvidence(
            source=EvidenceSource.MODEL_PREDICTION,
            evidence_type=EvidenceType.SHAP_FACTOR,
            label="High Energy Feature",
            value=0.25,
            strength=EvidenceStrength.STRONG,
            supporting_text="Worker fell from scaffolding",
            caveat="SHAP values show mathematical model contribution, not causality.",
            provenance="tree_shap_v1",
        )
        d = ev.to_dict()
        assert d["source"] == EvidenceSource.MODEL_PREDICTION
        assert d["evidence_type"] == EvidenceType.SHAP_FACTOR
        assert d["value"] == 0.25
        assert d["strength"] == "strong"
        assert d["caveat"] == "SHAP values show mathematical model contribution, not causality."

    def test_evidence_builder_helpers(self):
        # SHAP builder
        shap_ev = evidence_from_shap({"feature": "energy_type_pressure", "contribution": 0.12})
        assert shap_ev.evidence_type == EvidenceType.SHAP_FACTOR
        assert shap_ev.strength == EvidenceStrength.STRONG
        assert "SHAP values" in shap_ev.caveat

        # Field builder
        field_ev = evidence_from_incident_field("department", "Drilling")
        assert field_ev.source == EvidenceSource.INCIDENT_RECORD
        assert field_ev.label == "Department"
        assert field_ev.value == "Drilling"

        # IOGP tag builder
        iogp_ev = evidence_from_iogp_tag({"rule": "Confined Space", "confidence": 1.0, "matched_keywords": ["tank entry"]})
        assert iogp_ev.evidence_type == EvidenceType.RULE_MATCH
        assert iogp_ev.supporting_text == "tank entry"

        # Similar incident builder
        sim_ev = evidence_from_similar_incident({"incident_id": "12345", "similarity_score": 0.88, "narrative_excerpt": "Tank maintenance"})
        assert sim_ev.source == EvidenceSource.SEMANTIC_SIMILARITY
        assert sim_ev.value == 0.88

        # Recurrence builder
        rec_ev = evidence_from_recurrence_pattern({"rule": "Hot Work", "site": "Refinery", "occurrence_count": 4})
        assert rec_ev.source == EvidenceSource.RECURRENCE_PATTERN
        assert rec_ev.value == 4

        # Control status builder
        ctrl_ev = evidence_from_control_status("loto_isolation", "failed", True)
        assert ctrl_ev.source == EvidenceSource.BARRIER_INTELLIGENCE
        assert ctrl_ev.strength == EvidenceStrength.STRONG


# ── 7. Decision Trace & Serialization Integration ─────────────────────────────

@pytest.mark.django_db
class TestDecisionTraceAndSerializationIntegration:
    def test_build_analytical_assessment_includes_canonical_evidence_and_normalization(self):
        inc = Incident.objects.create(
            description="Worker was entering a confined vessel without atmospheric testing.",
            composite_narrative="Worker was entering a confined vessel without atmospheric testing.",
            department="refinery ops",
            location="tankfarm",
            job_task="vessel entry",
            equipment_involved="Pressure Vessel PV-101",
            energy_type="chemical",
            control_type="permit_isolation",
            control_condition="bypassed",
            control_failed_bypassed=True,
        )
        IOGPRuleTag.objects.create(
            incident=inc,
            rule="Confined Space",
            matched_keywords=["vessel entry"],
            matched_fields=["description"],
            confidence=1.0,
        )

        assessment = build_analytical_assessment(inc)

        # Existing keys must still exist without modification
        for key in ["data_quality", "psif_model", "iogp", "similarity", "recurrence", "incident_evidence", "provenance"]:
            assert key in assessment, f"Missing original key: {key}"

        # New canonical keys must exist
        assert "normalized_entities" in assessment
        assert "canonical_evidence" in assessment
        assert "methodology_disclosures" in assessment

        norm = assessment["normalized_entities"]
        assert norm["department"]["canonical_value"] == "Refinery Operations"
        assert norm["site"]["canonical_value"] == "Tank Farm"
        assert norm["activity"]["canonical_value"] == "Confined Space Vessel Entry"

        # Check canonical evidence contains structured records
        evidence_sources = {ev["source"] for ev in assessment["canonical_evidence"]}
        assert EvidenceSource.INCIDENT_RECORD in evidence_sources
        assert EvidenceSource.IOGP_CLASSIFICATION in evidence_sources
        assert EvidenceSource.BARRIER_INTELLIGENCE in evidence_sources

    def test_incident_detail_serializer_includes_normalized_entities(self):
        inc = Incident.objects.create(
            description="Testing pump maintenance",
            composite_narrative="Testing pump maintenance",
            department="mech maint",
            location="workshop",
        )
        serializer = IncidentDetailSerializer(inc)
        data = serializer.data
        assert "normalized_entities" in data
        assert data["normalized_entities"]["department"]["canonical_value"] == "Mechanical Maintenance"
        assert data["normalized_entities"]["site"]["canonical_value"] == "Workshop/Maintenance Bay"
        # Verify raw department is preserved in root serializer fields
        assert data["department"] == "mech maint"

    def test_recurrence_detection_enrichment(self):
        """detect_recurring_patterns produces canonical fields without breaking existing schema."""
        inc = Incident.objects.create(
            description="Lifting pipe with crane",
            composite_narrative="Lifting pipe with crane",
            department="Drilling",
            job_task="lifting",
        )
        IOGPRuleTag.objects.create(
            incident=inc,
            rule="Safe Mechanical Lifting",
            matched_keywords=["lifting"],
            matched_fields=["description"],
        )

        patterns = detect_recurring_patterns(window_days=90, min_occurrences=1, site="Drilling")
        assert len(patterns) >= 1
        p = patterns[0]
        assert "site" in p
        assert "canonical_site" in p
        assert p["canonical_site"] == "Drilling"
        assert "canonical_rule" in p
        assert p["canonical_rule"] == "Safe Mechanical Lifting"
        assert "normalized_entities" in p

    def test_incident_detail_view_renders_canonical_and_methodology_badges(self, client, django_user_model):
        """IncidentDetailView renders canonical entity tags and methodology badges."""
        user = django_user_model.objects.create_user(
            username="safety_tester",
            password="testpassword123",
            role="safety_officer"
        )
        client.login(username="safety_tester", password="testpassword123")

        inc = Incident.objects.create(
            description="Worker observed gas leak during hot tap operations",
            composite_narrative="Worker observed gas leak during hot tap operations",
            department="refinery ops",
            location="tankfarm",
            equipment_involved="Chemical Pump CP-12",
        )
        IOGPRuleTag.objects.create(
            incident=inc,
            rule="Hot Work",
            matched_keywords=["hot tap"],
            matched_fields=["description"],
            confidence=1.0,
        )

        url = reverse("incidents:detail", kwargs={"pk": inc.id})
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode("utf-8")

        # Canonical entity badges
        assert "Canonical: Refinery Operations" in content
        assert "Canonical: Tank Farm" in content
        assert "Class: Chemical Pump" in content

        # Methodology badges
        assert 'data-methodology-key="data_quality"' in content
        assert 'data-methodology-key="psif_model"' in content
        assert 'data-methodology-key="iogp"' in content


# ── 8. Barrier Intelligence View Tests ────────────────────────────────────────

@pytest.mark.django_db
class TestBarrierIntelligenceView:
    def test_barrier_intelligence_view_requires_auth(self, client):
        url = reverse("dashboard:barriers")
        response = client.get(url)
        assert response.status_code == 302
        assert "/accounts/login/" in response.url

    def test_barrier_intelligence_view_renders_correctly(self, client, django_user_model):
        user = django_user_model.objects.create_user(
            username="barrier_tester",
            password="testpassword123",
            role="analyst"
        )
        client.login(username="barrier_tester", password="testpassword123")

        url = reverse("dashboard:barriers")
        response = client.get(url)
        assert response.status_code == 200
        content = response.content.decode("utf-8")

        # Page title and headers
        assert "Barrier &amp; Critical-Control Intelligence" in content or "Barrier & Critical-Control Intelligence" in content
        assert "Monitored Barriers" in content
        assert "Matched Observations" in content
        assert "PSIF-Linked Reports" in content
        assert "Reporting Sites" in content

        # Methodology disclosure and data integrity note
        assert "Barrier associations are derived from deterministic IOGP Life-Saving Rules" in content
        assert "Concern-pattern matches: NOT CURRENTLY COMPUTABLE (Omitted)" in content

        # Chart container
        assert 'id="barrierComparisonChart"' in content


# ── 9. Hardened Shared Intelligence Foundation Contracts ─────────────────────

@pytest.mark.django_db
class TestHardenedFoundationContracts:
    """
    Validates the strict contracts established in Task 1:
    - Conservative normalization (methods, statuses, properties, ambiguity)
    - 9 Centralized methodology notices with exact wording
    - Analytical evidence backlinks and deterministic serialization
    - Runtime version manifest introspection
    - Public facade imports
    """

    def test_canonical_normalization_statuses_and_methods(self):
        from apps.incidents.services.normalization import NormalizationMethod, NormalizationStatus

        # Canonical method vocabulary
        assert NormalizationMethod.EXACT_ALIAS == "exact_alias"
        assert NormalizationMethod.NORMALIZED == "normalized"
        assert NormalizationMethod.BOUNDED_FUZZY == "bounded_fuzzy"
        assert NormalizationMethod.IDENTITY == "identity"
        assert NormalizationMethod.UNKNOWN == "unknown"

        # Canonical status vocabulary
        assert NormalizationStatus.CANONICAL == "canonical"
        assert NormalizationStatus.MAPPED == "mapped"
        assert NormalizationStatus.SUGGESTED == "suggested"
        assert NormalizationStatus.UNCERTAIN == "uncertain"
        assert NormalizationStatus.UNKNOWN == "unknown"

        # Compatibility aliases preserved
        assert NormalizationMethod.EXACT_CANONICAL == "normalized"
        assert NormalizationMethod.NORMALIZED_SYNTAX == "normalized"
        assert NormalizationMethod.UNMAPPED == "unknown"
        assert NormalizationStatus.RESOLVED == "mapped"
        assert NormalizationStatus.UNMAPPED == "unknown"

    def test_normalized_entity_boolean_properties(self):
        from apps.incidents.services import (
            normalize_location,
            normalize_department,
            normalize_barrier,
            NormalizedEntity,
            NormalizationMethod,
            NormalizationStatus,
        )

        # Exact canonical
        can_ent = normalize_location("Tank Farm")
        assert can_ent.is_canonical is True
        assert can_ent.is_mapped is False
        assert can_ent.is_uncertain is False

        # Exact alias
        alias_ent = normalize_department("refinery ops")
        assert alias_ent.is_mapped is True
        assert alias_ent.canonical_value == "Refinery Operations"
        assert alias_ent.is_canonical is False

        # Fuzzy suggestion
        fuzzy_ent = normalize_location("Compressor Statn")
        assert fuzzy_ent.is_suggested is True
        assert fuzzy_ent.status == NormalizationStatus.SUGGESTED

        # Unknown / Empty
        unk_ent = normalize_barrier(None)
        assert unk_ent.is_unknown is True
        assert unk_ent.method == NormalizationMethod.UNKNOWN
        assert unk_ent.status == NormalizationStatus.UNKNOWN

    def test_barrier_and_asset_normalization_helpers(self):
        from apps.incidents.services import normalize_barrier, normalize_asset

        # Barrier helper
        bar_res = normalize_barrier("loto")
        assert bar_res.canonical_value == "LOTO / Energy Isolation (Direct)"
        assert bar_res.is_mapped is True

        # Asset helper with tag extraction
        asset_res = normalize_asset("Chemical Pump CP-12")
        assert asset_res.canonical_value == "Chemical Pump"
        assert asset_res.metadata.get("asset_tag") == "CP-12"
        assert asset_res.is_mapped is True

    def test_strict_conservative_fuzzy_never_silent_mapped(self):
        """Fuzzy similarity matches must remain explicit SUGGESTED and never silently authoritative."""
        from apps.incidents.services import normalize_location, NormalizationStatus, NormalizationMethod
        res = normalize_location("Compressor Statn")
        assert res.canonical_value == "Compressor Station"
        assert res.method == NormalizationMethod.BOUNDED_FUZZY
        assert res.status == NormalizationStatus.SUGGESTED
        assert res.is_suggested is True

    def test_all_nine_canonical_methodology_notices_exact_wording(self):
        """Verifies all 9 canonical methodology disclosures meet Section 4 requirements verbatim."""
        from apps.incidents.services import get_methodology_notice, MethodologyKey

        expected_summaries = {
            MethodologyKey.PSIF_MODEL: "PSIF Model Score from the active model; score is not a calibrated probability.",
            MethodologyKey.IOGP: "Rule-derived candidate from deterministic keyword/phrase matching; not calibrated confidence or proof of control failure.",
            MethodologyKey.SIMILARITY: "Semantic similarity between incident narratives; not causal evidence or duplicate identity.",
            MethodologyKey.RECURRENCE: "Historical recurrence based on normalized entities and time-window matching; not causal/systemic prediction.",
            MethodologyKey.SHAP: "SHAP values show mathematical model contribution, not causality.",
            MethodologyKey.HUMAN_REVIEW: "Human adjudication is shown separately from model prediction.",
            MethodologyKey.DATA_QUALITY: "Data-quality rules indicate analytical suitability; they do not establish PSIF status.",
            MethodologyKey.BARRIER: "Rule-derived candidate from deterministic keyword/phrase matching; not calibrated confidence or proof of control failure.",
            MethodologyKey.CROSS_SITE: "Cross-site findings use normalized safety entities and historical occurrence data. They indicate recurrence patterns, not causal relationships or future-risk predictions.",
        }

        for key, expected_summary in expected_summaries.items():
            notice = get_methodology_notice(key)
            assert notice["key"] == key
            assert notice["summary"] == expected_summary, f"Mismatch on methodology key: {key}"

    def test_analytical_evidence_backlinks_and_deterministic_dict(self):
        from apps.incidents.services import (
            AnalyticalEvidence,
            EvidenceSource,
            EvidenceType,
            EvidenceStrength,
            evidence_from_cross_site,
        )

        ev = AnalyticalEvidence(
            source=EvidenceSource.MODEL_PREDICTION,
            evidence_type=EvidenceType.SHAP_FACTOR,
            label="Pressure Hazard Impact",
            value=0.18,
            strength=EvidenceStrength.STRONG,
            field_name="energy_type",
            supporting_text="High pressure gas line ruptured",
            provenance="tree_shap_explainer_v1",
            metadata={"source_document": "Incident Report #44"},
        )

        # Backlink properties
        assert ev.incident_field == "energy_type"
        assert ev.analytical_component == EvidenceSource.MODEL_PREDICTION
        assert ev.model_version == "tree_shap_explainer_v1"
        assert ev.source_document == "Incident Report #44"

        # Deterministic dictionary serialization
        d = ev.to_dict()
        assert list(d.keys()) == sorted(d.keys())
        assert d["incident_field"] == "energy_type"
        assert d["analytical_component"] == EvidenceSource.MODEL_PREDICTION
        assert d["model_version"] == "tree_shap_explainer_v1"
        assert d["source_document"] == "Incident Report #44"

        # Cross-site builder
        cross_ev = evidence_from_cross_site({
            "rule": "Line of Fire",
            "site": "Refinery Bay",
            "occurrence_count": 4,
            "summary_text": "Repeated line of fire events across regional sites",
        })
        assert cross_ev.source == EvidenceSource.CROSS_SITE
        assert cross_ev.evidence_type == EvidenceType.CROSS_SITE_MATCH
        assert cross_ev.strength == EvidenceStrength.STRONG
        assert "Cross-site findings use normalized safety entities" in cross_ev.caveat

    def test_authoritative_runtime_version_manifest(self):
        from apps.incidents.services import get_intelligence_foundation_versions

        versions = get_intelligence_foundation_versions()
        required_keys = [
            "model_version",
            "knowledge_base_version",
            "reasoning_ruleset_version",
            "action_library_version",
            "data_quality_version",
            "normalization_version",
        ]
        for rk in required_keys:
            assert rk in versions, f"Missing version key: {rk}"
            assert isinstance(versions[rk], str)
            assert len(versions[rk]) > 0

        assert versions["knowledge_base_version"] == "psif_kb_v1.0"
        assert versions["reasoning_ruleset_version"] == "psif_ruleset_v1.0"
        assert versions["action_library_version"] == "action_library_v1"
        assert versions["data_quality_version"] == "incident_quality_v1"
        assert versions["normalization_version"] == "deterministic_taxonomy_v1"

    def test_public_facade_reexports(self):
        import apps.incidents.services as facade

        # Normalization
        assert hasattr(facade, "normalize_entity")
        assert hasattr(facade, "normalize_barrier")
        assert hasattr(facade, "normalize_asset")
        assert hasattr(facade, "NormalizedEntity")

        # Methodology
        assert hasattr(facade, "get_methodology_notice")
        assert hasattr(facade, "MethodologyKey")

        # Evidence
        assert hasattr(facade, "AnalyticalEvidence")
        assert hasattr(facade, "evidence_from_cross_site")

        # Knowledge Base & Reasoning
        assert hasattr(facade, "KNOWLEDGE_BASE_VERSION")
        assert hasattr(facade, "REASONING_RULESET_VERSION")

        # Actions & DQ
        assert hasattr(facade, "ACTION_LIBRARY_VERSION")
        assert hasattr(facade, "DATA_QUALITY_VERSION")

