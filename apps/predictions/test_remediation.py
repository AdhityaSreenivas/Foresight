from datetime import date
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.test.utils import CaptureQueriesContext
from django.db import connection

from apps.datasets.models import Dataset
from apps.incidents.models import Incident, incident_to_prediction_record
from apps.predictions.models import ModelVersion, PredictionResult
from ml_engine.text_preprocessing import is_sparse_narrative

User = get_user_model()


class SparseRuleTests(TestCase):
    """Regression tests for Phase 3: canonical sparse narrative rule."""

    def test_empty_and_whitespace_are_sparse(self):
        self.assertTrue(is_sparse_narrative(None))
        self.assertTrue(is_sparse_narrative(""))
        self.assertTrue(is_sparse_narrative("   \t\n  "))

    def test_punctuation_only_is_sparse(self):
        self.assertTrue(is_sparse_narrative("... ... !!! ,,, ;;;"))
        self.assertTrue(is_sparse_narrative("--- --- ***"))

    def test_under_ten_words_are_sparse(self):
        self.assertTrue(is_sparse_narrative("worker fell"))
        nine_words = "one two three four five six seven eight nine"
        self.assertTrue(is_sparse_narrative(nine_words))

    def test_ten_and_more_words_are_not_sparse(self):
        ten_words = "one two three four five six seven eight nine ten"
        self.assertFalse(is_sparse_narrative(ten_words))

        eleven_words = "one two three four five six seven eight nine ten eleven"
        self.assertFalse(is_sparse_narrative(eleven_words))

    def test_words_with_punctuation(self):
        # 10 words with commas/hyphens should count as 10 words
        text = "High-pressure valve ruptured, injuring technician standing nearby without barrier protection in place."
        self.assertFalse(is_sparse_narrative(text))


class CanonicalMappingAndLeakageTests(TestCase):
    """Regression tests for Phase 2: canonical record mapping and leakage prevention."""

    def setUp(self):
        self.incident = Incident.objects.create(
            description="Operator slipped from ladder while accessing crane cab.",
            corrective_actions="Replace ladder rungs and add fall arrestor.",
            witness_statement="I saw him lose balance on the 3rd step.",
            department="Maintenance",
            location="Drill Site 4",
            job_task="Accessing crane cab",
            equipment_involved="Crane 102",
            injury_type="Fracture",
            body_part="Left Leg",
            immediate_cause="Slippery rung",
            root_cause_category="Equipment Failure",
            near_miss=False,
            report_type=Incident.ReportType.INCIDENT,
            high_energy_present=Incident.SafetyContextState.YES,
            energy_type=Incident.EnergyType.GRAVITY_HEIGHT,
            worker_exposed=Incident.SafetyContextState.YES,
            direct_control_present=Incident.SafetyContextState.NO,
            control_type=Incident.ControlType.FALL_PROTECTION,
            control_condition=Incident.ControlCondition.ABSENT,
            control_failed_bypassed=False,
            # Target / source / human fields
            severity_actual=Incident.SeverityActual.LOST_TIME,
            severity_potential=Incident.SeverityPotential.SERIOUS,
            is_psif_human_label=None,
            raw_row={
                "report_text": "Operator slipped from ladder",
                "activity": "Accessing crane cab",
                "site_area": "Drill Site 4",
                "sif_label": 1,
                "sif_category": "Fall from height",
                "confidence_target": 0.95,
                "reason": "Fall hazard",
                "evidence_phrases": ["crane cab", "ladder"],
                "barrier_failures": ["fall protection"],
                "life_saving_rule": "Working at height",
            },
        )

    def test_canonical_record_shape(self):
        rec = incident_to_prediction_record(self.incident)
        self.assertEqual(rec["description"], self.incident.description)
        self.assertEqual(rec["corrective_actions"], self.incident.corrective_actions)
        self.assertEqual(rec["witness_statement"], self.incident.witness_statement)
        self.assertEqual(rec["department"], "Maintenance")
        self.assertEqual(rec["job_task"], "Accessing crane cab")
        self.assertEqual(rec["energy_type"], Incident.EnergyType.GRAVITY_HEIGHT)
        self.assertEqual(rec["high_energy_present"], Incident.SafetyContextState.YES)

    def test_no_target_or_human_review_fields_in_record(self):
        rec = incident_to_prediction_record(self.incident)
        prohibited_keys = {
            "severity_actual",
            "severity_potential",
            "is_psif_human_label",
            "is_psif_heuristic_label",
            "sif_label",
            "sif_category",
            "confidence_target",
            "reason",
            "evidence_phrases",
            "barrier_failures",
            "life_saving_rule",
            "reviewer_rationale",
            "reviewed_by",
            "reviewed_at",
            "raw_row",
        }
        for key in prohibited_keys:
            self.assertNotIn(key, rec, f"Prohibited key '{key}' found in canonical prediction record!")


class TriageQueueScalabilityTests(TestCase):
    """Regression tests for Phase 9 & 10: Triage queue server-side pagination and performance."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="reviewer_user",
            password="testpassword123",
            role=User.Role.SAFETY_OFFICER,
        )
        self.client.login(username="reviewer_user", password="testpassword123")

        self.dataset = Dataset.objects.create(
            name="Test Triage Dataset",
            file_type=Dataset.FileType.JSONL,
            status=Dataset.Status.COMPLETED,
            total_rows=60,
            processed_rows=60,
        )

        self.model_version = ModelVersion.objects.create(
            version_label="test_v1",
            bert_model_name="distilbert-base-uncased",
            xgboost_artifact_path="ml_engine/artifacts/test_v1/model.json",
            encoder_artifact_path="ml_engine/artifacts/test_v1/encoders.joblib",
            is_active=True,
        )

        # Create 60 pending incidents with predictions
        incidents = [
            Incident(
                dataset=self.dataset,
                status=Incident.Status.PENDING,
                description=f"Incident report description narrative number {i} for testing queue.",
                department="Electrical" if i % 2 == 0 else "Drilling",
                incident_date=date(2026, 1, 1),
            )
            for i in range(60)
        ]
        created = Incident.objects.bulk_create(incidents)

        predictions = [
            PredictionResult(
                incident=inc,
                model_version=self.model_version,
                psif_probability=0.85 if i % 2 == 0 else 0.15,
                psif_predicted=(i % 2 == 0),
                risk_level="high" if i % 2 == 0 else "low",
                evidence_strength="Strong" if i % 2 == 0 else "Weak",
                is_sparse_input=False,
                top_factors=[{"feature": "department", "contribution": 0.2}],
                explanation_detail={"high_energy_source": {"identified": i % 2 == 0}},
            )
            for i, inc in enumerate(created)
        ]
        PredictionResult.objects.bulk_create(predictions)

    def test_default_pagination_is_50(self):
        url = reverse("predictions:review_queue")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        self.assertTrue(response.context["is_paginated"])
        self.assertEqual(len(response.context["incidents"]), 50)
        self.assertEqual(response.context["paginator"].count, 60)
        self.assertEqual(response.context["paginator"].num_pages, 2)

    def test_page_size_options_25_and_100(self):
        url = reverse("predictions:review_queue")

        # 25 rows
        resp_25 = self.client.get(f"{url}?page_size=25")
        self.assertEqual(len(resp_25.context["incidents"]), 25)
        self.assertEqual(resp_25.context["paginator"].num_pages, 3)

        # 100 rows
        resp_100 = self.client.get(f"{url}?page_size=100")
        self.assertEqual(len(resp_100.context["incidents"]), 60)
        self.assertFalse(resp_100.context["is_paginated"])

    def test_filter_psif_candidates_only(self):
        url = reverse("predictions:review_queue")
        response = self.client.get(f"{url}?psif=true")
        self.assertEqual(response.status_code, 200)
        # Out of 60, exactly 30 are PSIF
        self.assertEqual(response.context["paginator"].count, 30)
        for inc in response.context["incidents"]:
            self.assertTrue(inc.prediction.psif_predicted)

    def test_query_count_is_bounded(self):
        """
        Query count must be bounded and strictly O(1) with respect to rows in the table.
        It must not issue N+1 queries for each incident.
        """
        url = reverse("predictions:review_queue")
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)

        # 1 query for session/user auth
        # 1 query for paginator count
        # 1 query for page items (with select_related)
        # 1 query for prefetch_related(iogp_rules)
        # Total queries should be <= 10, nowhere near 50 or 60!
        query_count = len(queries)
        self.assertLessEqual(
            query_count, 10,
            f"Expected bounded query count (<= 10), but executed {query_count} queries!"
        )

    def test_empty_state_rendered_when_no_match(self):
        url = reverse("predictions:review_queue")
        response = self.client.get(f"{url}?department=NonExistentDepartment")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No Incidents Match the Current Filters")
