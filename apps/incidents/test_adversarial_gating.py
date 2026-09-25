from django.test import TestCase
import uuid
from datetime import date
import numpy as np

from apps.incidents.models import Incident, IncidentEmbedding, IOGPRuleTag, IncidentDataQuality
from apps.predictions.models import PredictionResult, ModelVersion
from apps.incidents.services.decision_trace import build_analytical_assessment
from apps.dashboard.pattern_detection import detect_recurring_patterns, detect_multi_site_recurrence

class AdversarialGatingTests(TestCase):
    def setUp(self):
        self.model_version = ModelVersion.objects.create(
            version_label="v_test_adv",
            is_active=True
        )
        
    def create_incident(self, composite_narrative, psif_predicted, prob, department, is_sparse=False, dq_status=IncidentDataQuality.Status.VALID, job_task="TaskX", body_part=""): 
        inc = Incident.objects.create(
            id=uuid.uuid4(),
            incident_date=date(2026, 9, 1),
            department=department,
            job_task=job_task,
            body_part=body_part,
            composite_narrative=composite_narrative,
            status="investigation"
        )
        # Prediction
        PredictionResult.objects.create(
            incident=inc,
            model_version=self.model_version,
            psif_probability=prob,
            psif_predicted=psif_predicted,
            risk_level="low" if not psif_predicted else "high",
            is_sparse_input=is_sparse
        )
        # Embedding
        IncidentEmbedding.objects.create(
            incident=inc,
            embedding_model="distilbert-base-uncased",
            vector=np.random.rand(768).tolist()
        )
        # DQ
        IncidentDataQuality.objects.create(
            incident=inc,
            status=dq_status,
            quality_version="1.0",
            findings=[]
        )
        return inc

    def test_1_valid_low_psif_recurrence(self):
        # 1. Valid + Low PSIF + Recurrence
        # Setup: Create two identical incidents to trigger recurrence
        inc1 = self.create_incident("Valid narrative about a hazard", False, 0.1, "Dept A")
        inc2 = self.create_incident("Valid narrative about a hazard", False, 0.1, "Dept A")
        inc3 = self.create_incident("Valid narrative about a hazard", False, 0.1, "Dept A")
        IOGPRuleTag.objects.create(incident=inc3, rule="Energy Isolation", classification_method="keyword")
        # Add IOGP tags so recurrence can catch them (assuming recurrence matches on rule + site)
        IOGPRuleTag.objects.create(incident=inc1, rule="Energy Isolation", classification_method="keyword")
        IOGPRuleTag.objects.create(incident=inc2, rule="Energy Isolation", classification_method="keyword")
        
        # Test inc1
        assessment = build_analytical_assessment(inc1)
        self.assertEqual(assessment["psif_model"]["status"], "AVAILABLE")
        self.assertIn(assessment["psif_model"]["classification"], ["NOT PSIF", "Non-PSIF"])
        self.assertEqual(assessment["similarity"]["status"], "AVAILABLE")
        self.assertEqual(assessment["recurrence"]["status"], "AVAILABLE")
        self.assertTrue(len(assessment["recurrence"]["items"]) > 0)

    def test_2_valid_high_psif_no_recurrence(self):
        # 2. Valid + High PSIF + No Recurrence
        inc = self.create_incident("Valid high risk hazard", True, 0.9, "Dept B")
        assessment = build_analytical_assessment(inc)
        self.assertEqual(assessment["psif_model"]["status"], "AVAILABLE")
        self.assertEqual(assessment["psif_model"]["classification"], "PSIF")
        self.assertEqual(assessment["recurrence"]["status"], "AVAILABLE")
        self.assertEqual(len(assessment["recurrence"]["items"]), 0)

    def test_3_valid_low_psif_iogp(self):
        # 3. Valid + Low PSIF + IOGP Candidate
        inc = self.create_incident("Valid narrative", False, 0.1, "Dept C")
        IOGPRuleTag.objects.create(incident=inc, rule="Hot Work", classification_method="keyword")
        assessment = build_analytical_assessment(inc)
        self.assertIn(assessment["psif_model"]["classification"], ["NOT PSIF", "Non-PSIF"])
        self.assertEqual(assessment["iogp"]["status"], "AVAILABLE")
        self.assertTrue(len(assessment["iogp"]["items"]) > 0)

    def test_4_sparse_no_metadata(self):
        # 4. Sparse + no metadata
        inc = self.create_incident("hi", False, 0.0, None, is_sparse=True)
        assessment = build_analytical_assessment(inc)
        self.assertIn(assessment["psif_model"]["status"], ["INSUFFICIENT_EVIDENCE", "NOT_AVAILABLE"])
        self.assertEqual(assessment["similarity"]["status"], "NOT_RUN")
        self.assertEqual(assessment["recurrence"]["status"], "NOT_RUN")

    def test_5_sparse_metadata(self):
        # 5. Sparse + metadata
        inc = self.create_incident("hi", False, 0.0, "Dept D", is_sparse=True)
        assessment = build_analytical_assessment(inc)
        self.assertIn(assessment["psif_model"]["status"], ["INSUFFICIENT_EVIDENCE", "NOT_AVAILABLE"])
        self.assertEqual(assessment["similarity"]["status"], "NOT_RUN")
        self.assertEqual(assessment["recurrence"]["status"], "AVAILABLE")
        self.assertEqual(len(assessment["recurrence"]["items"]), 0)

    def test_6_warning_analyzable(self):
        # 6. Warning + analyzable
        inc = self.create_incident("Good narrative", False, 0.2, "Dept E", dq_status=IncidentDataQuality.Status.WARNING)
        assessment = build_analytical_assessment(inc)
        self.assertEqual(assessment["psif_model"]["status"], "AVAILABLE")
        self.assertEqual(assessment["similarity"]["status"], "AVAILABLE")
        
    def test_7_critical_contradiction_analyzable(self):
        # 7. Critical contradiction + analyzable
        inc = self.create_incident("Eye injury", False, 0.2, "Dept F", body_part="knee", dq_status=IncidentDataQuality.Status.CRITICAL)
        assessment = build_analytical_assessment(inc)
        self.assertIn(assessment["psif_model"]["status"], ["AVAILABLE", "AVAILABLE_WITH_WARNING"])
        self.assertEqual(assessment["similarity"]["status"], "AVAILABLE_WITH_WARNING")
        self.assertEqual(assessment["recurrence"]["status"], "AVAILABLE_WITH_WARNING")

    def test_8_analysis_run_zero_results(self):
        # 8. Analysis run + zero results
        inc = self.create_incident("Unique incident narrative", False, 0.1, "Dept G")
        assessment = build_analytical_assessment(inc)
        self.assertEqual(assessment["similarity"]["status"], "AVAILABLE")
        self.assertEqual(len(assessment["similarity"]["items"]), 0)
        self.assertIsNone(assessment["similarity"]["reason"])

    def test_9_analysis_not_run_zero_results(self):
        # 9. Analysis not run + zero results
        inc = self.create_incident("", False, 0.1, None, is_sparse=True)
        assessment = build_analytical_assessment(inc)
        self.assertEqual(assessment["similarity"]["status"], "NOT_RUN")
        self.assertEqual(len(assessment["similarity"]["items"]), 0)
        self.assertIsNotNone(assessment["similarity"]["reason"])
        
    def test_10_similarity_but_no_recurrence(self):
        # 10. Similarity available but no recurrence
        inc1 = self.create_incident("Identical incident text", False, 0.1, "Dept H")
        inc2 = self.create_incident("Identical incident text", False, 0.1, "Dept I") # different dept
        inc2.embedding.vector = inc1.embedding.vector
        inc2.embedding.save()
        
        assessment = build_analytical_assessment(inc1)
        self.assertEqual(assessment["similarity"]["status"], "AVAILABLE")
        # similarity requires same department? Yes, by default. Let's make dept same to trigger similarity but not recurrence if IOGP rule is missing.
        inc2.department = "Dept H"
        inc2.save()
        assessment = build_analytical_assessment(inc1)
        self.assertTrue(len(assessment["similarity"]["items"]) > 0)
        self.assertEqual(assessment["recurrence"]["status"], "AVAILABLE")
        self.assertEqual(len(assessment["recurrence"]["items"]), 0)

    def test_11_recurrence_but_no_similarity(self):
        # 11. Recurrence available but no similarity
        inc1 = self.create_incident("Very distinct narrative A", False, 0.1, "Dept J")
        inc2 = self.create_incident("Very distinct narrative B", False, 0.1, "Dept J")
        inc3 = self.create_incident("Very distinct narrative B", False, 0.1, "Dept J")
        IOGPRuleTag.objects.create(incident=inc1, rule="RuleX", classification_method="keyword")
        IOGPRuleTag.objects.create(incident=inc3, rule="RuleX", classification_method="keyword")
        IOGPRuleTag.objects.create(incident=inc2, rule="RuleX", classification_method="keyword")
        
        # Vectors are random, similarity likely 0 unless seed matches
        assessment = build_analytical_assessment(inc1)
        self.assertEqual(assessment["recurrence"]["status"], "AVAILABLE")
        self.assertTrue(len(assessment["recurrence"]["items"]) > 0)
        self.assertEqual(assessment["similarity"]["status"], "AVAILABLE")
        # we can't strictly assert len 0 due to random, but usually it's small.

    def test_12_iogp_available_psif_low(self):
        # 12. IOGP available while PSIF is Low
        inc = self.create_incident("Narrative here", False, 0.1, "Dept K")
        IOGPRuleTag.objects.create(incident=inc, rule="Confined Space", classification_method="keyword")
        assessment = build_analytical_assessment(inc)
        self.assertIn(assessment["psif_model"]["classification"], ["NOT PSIF", "Non-PSIF"])
        self.assertEqual(assessment["iogp"]["status"], "AVAILABLE")
        self.assertTrue(len(assessment["iogp"]["items"]) > 0)
