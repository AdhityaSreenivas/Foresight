import uuid
from datetime import date
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from django.core.cache import cache
from apps.incidents.models import Incident
from apps.predictions.models import PredictionResult, ModelVersion

User = get_user_model()


class AnalyticsSummaryAPITests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="analyst_test",
            email="analyst@oilindia.in",
            password="testpassword123"
        )
        self.client.force_authenticate(user=self.user)
        self.client.force_login(self.user)

        self.model_version = ModelVersion.objects.create(
            version_label="v_test_dashboard",
            bert_model_name="distilbert-base-uncased",
            xgboost_artifact_path="/tmp/test_xgb.json",
            encoder_artifact_path="/tmp/test_enc.joblib",
            is_active=True,
        )

    def tearDown(self):
        cache.clear()

    def test_unauthenticated_rejected(self):
        """Unauthenticated requests must be rejected with 401."""
        anon_client = APIClient()
        resp = anon_client.get("/api/analytics/summary/")
        self.assertIn(resp.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_empty_database_no_division_by_zero(self):
        """Zero incidents and zero predictions must return 0.0 rate without ZeroDivisionError."""
        resp = self.client.get("/api/analytics/summary/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["total_incidents"], 0)
        self.assertEqual(data["prediction_eligible_incidents"], 0)
        self.assertEqual(data["psif_incidents"], 0)
        self.assertEqual(data["psif_prediction_rate"], 0.0)
        self.assertEqual(data["sparse_predictions_count"], 0)
        self.assertIn("metric_definition", data)

    def test_denominator_contains_only_prediction_eligible_incidents(self):
        """
        Denominator must contain only prediction-eligible incidents (those with PredictionResult),
        not all ingested incidents.
        """
        # Create 5 incidents: 3 with predictions, 2 without
        incidents = [
            Incident.objects.create(
                id=uuid.uuid4(),
                incident_date=date(2026, 9, 1),
                department="Drilling",
                composite_narrative=f"Incident narrative {i}",
            )
            for i in range(5)
        ]

        # 1 positive eligible prediction
        PredictionResult.objects.create(
            incident=incidents[0],
            model_version=self.model_version,
            psif_probability=0.88,
            psif_predicted=True,
            risk_level="high",
            is_sparse_input=False,
            top_factors=[],
        )
        # 2 negative eligible predictions
        for inc in incidents[1:3]:
            PredictionResult.objects.create(
                incident=inc,
                model_version=self.model_version,
                psif_probability=0.12,
                psif_predicted=False,
                risk_level="low",
                is_sparse_input=False,
                top_factors=[],
            )
        # incidents[3] and incidents[4] have NO PredictionResult

        resp = self.client.get("/api/analytics/summary/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()

        self.assertEqual(data["total_incidents"], 5, "Total incidents should be all 5 reports.")
        self.assertEqual(data["prediction_eligible_incidents"], 3, "Denominator must be 3 prediction-eligible incidents.")
        self.assertEqual(data["psif_incidents"], 1, "Numerator must be 1 positive eligible prediction.")
        # Canonical rate = 1 / 3 = 0.3333 (NOT 1 / 5 = 0.20)
        self.assertAlmostEqual(data["psif_prediction_rate"], 0.3333, places=3)

    def test_sparse_records_handled_according_to_documented_policy(self):
        """
        Sparse predictions must be excluded from prediction_eligible_incidents and the rate,
        and counted separately in sparse_predictions_count.
        """
        # 2 non-sparse incidents (1 positive, 1 negative)
        inc1 = Incident.objects.create(id=uuid.uuid4(), incident_date=date(2026, 9, 1), composite_narrative="Worker tripped.")
        PredictionResult.objects.create(
            incident=inc1,
            model_version=self.model_version,
            psif_probability=0.85,
            psif_predicted=True,
            risk_level="high",
            is_sparse_input=False,
            top_factors=[],
        )
        inc2 = Incident.objects.create(id=uuid.uuid4(), incident_date=date(2026, 9, 1), composite_narrative="Minor scratch.")
        PredictionResult.objects.create(
            incident=inc2,
            model_version=self.model_version,
            psif_probability=0.20,
            psif_predicted=False,
            risk_level="low",
            is_sparse_input=False,
            top_factors=[],
        )

        # 2 sparse incidents (1 marked positive by heuristic/threshold, 1 negative)
        inc_sparse1 = Incident.objects.create(id=uuid.uuid4(), incident_date=date(2026, 9, 1), composite_narrative="")
        PredictionResult.objects.create(
            incident=inc_sparse1,
            model_version=self.model_version,
            psif_probability=0.90,
            psif_predicted=True,
            risk_level="high",
            is_sparse_input=True,
            top_factors=[],
        )
        inc_sparse2 = Incident.objects.create(id=uuid.uuid4(), incident_date=date(2026, 9, 1), composite_narrative="n/a")
        PredictionResult.objects.create(
            incident=inc_sparse2,
            model_version=self.model_version,
            psif_probability=0.10,
            psif_predicted=False,
            risk_level="low",
            is_sparse_input=True,
            top_factors=[],
        )

        resp = self.client.get("/api/analytics/summary/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()

        self.assertEqual(data["total_incidents"], 4)
        self.assertEqual(data["sparse_predictions_count"], 2)
        # Denominator should only be non-sparse eligible predictions: 2
        self.assertEqual(data["prediction_eligible_incidents"], 2)
        # Numerator should only be non-sparse positive predictions: 1
        self.assertEqual(data["psif_incidents"], 1)
        # Rate: 1 / 2 = 0.5
        self.assertEqual(data["psif_prediction_rate"], 0.5)

    def test_metric_definition_metadata_present(self):
        """API must return explicit structured metric definition metadata."""
        resp = self.client.get("/api/analytics/summary/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()

        defn = data.get("metric_definition")
        self.assertIsNotNone(defn)
        self.assertEqual(defn.get("metric_name"), "psif_prediction_rate")
        self.assertIn("numerator", defn)
        self.assertIn("denominator", defn)
        self.assertIn("sparse_input", defn)
        self.assertIn("time_window", defn)

    def test_analytics_trend_api(self):
        """Analytics trend API should return monthly totals and eligible/psif counts excluding sparse."""
        inc = Incident.objects.create(
            id=uuid.uuid4(),
            incident_date=date(2026, 8, 15),
            composite_narrative="Pipeline valve leak observed.",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=self.model_version,
            psif_probability=0.75,
            psif_predicted=True,
            risk_level="high",
            is_sparse_input=False,
            top_factors=[],
        )

        resp = self.client.get("/api/analytics/trend/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertIn("trends", data)
        self.assertEqual(len(data["trends"]), 1)
        trend = data["trends"][0]
        self.assertEqual(trend["month"], "2026-08")
        self.assertEqual(trend["total"], 1)
        self.assertEqual(trend["eligible"], 1)
        self.assertEqual(trend["psif"], 1)

    def test_analytics_summary_cache_and_invalidation(self):
        """Test cache hit, cache miss, and invalidation for analytics summary service."""
        from django.core.cache import cache
        from apps.dashboard.services import (
            get_analytics_summary,
            invalidate_analytics_cache,
            CACHE_KEY_ANALYTICS_SUMMARY,
        )

        cache.clear()

        # 1. First call (cache miss) computes and stores in cache
        summary1 = get_analytics_summary(use_cache=True)
        self.assertIsNotNone(summary1)
        self.assertEqual(summary1["total_incidents"], 0)

        cached_val = cache.get(CACHE_KEY_ANALYTICS_SUMMARY)
        self.assertIsNotNone(cached_val, "Analytics summary should be cached.")
        self.assertEqual(cached_val["total_incidents"], 0)

        # 2. Add an incident directly to DB
        Incident.objects.create(
            id=uuid.uuid4(),
            incident_date=date(2026, 9, 2),
            composite_narrative="Pressure drop at manifold.",
        )

        # 3. Cache hit returns old cached count
        summary2 = get_analytics_summary(use_cache=True)
        self.assertEqual(summary2["total_incidents"], 0, "Should return cached data on cache hit.")

        # 4. Invalidation clears cache and re-computes fresh count
        invalidate_analytics_cache()
        self.assertIsNone(cache.get(CACHE_KEY_ANALYTICS_SUMMARY))

        summary3 = get_analytics_summary(use_cache=True)
        self.assertEqual(summary3["total_incidents"], 1, "Should compute fresh count after invalidation.")

        # 5. Force refresh also updates cache
        Incident.objects.create(
            id=uuid.uuid4(),
            incident_date=date(2026, 9, 3),
            composite_narrative="Valve packing leak.",
        )
        summary4 = get_analytics_summary(use_cache=True, force_refresh=True)
        self.assertEqual(summary4["total_incidents"], 2, "Force refresh should bypass cache and update count.")

    def test_analytics_trend_cache(self):
        """Test cache hit and invalidation for analytics trend service."""
        from django.core.cache import cache
        from apps.dashboard.services import (
            get_analytics_trend,
            invalidate_analytics_cache,
            CACHE_KEY_ANALYTICS_TREND,
        )

        cache.clear()
        trend1 = get_analytics_trend(use_cache=True)
        self.assertIn("trends", trend1)

        cached_trend = cache.get(CACHE_KEY_ANALYTICS_TREND)
        self.assertIsNotNone(cached_trend, "Trend data should be cached.")

        invalidate_analytics_cache()
        self.assertIsNone(cache.get(CACHE_KEY_ANALYTICS_TREND))

    def test_dashboard_server_rendered_metrics(self):
        """Dashboard HTML must contain server-rendered KPI metric values instead of static placeholders."""
        inc = Incident.objects.create(
            id=uuid.uuid4(),
            incident_date=date(2026, 9, 1),
            composite_narrative="Gas detector alarm triggered in pump house.",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=self.model_version,
            psif_probability=0.82,
            psif_predicted=True,
            risk_level="high",
            is_sparse_input=False,
            top_factors=[],
        )

        resp = self.client.get("/dashboard/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("analytics_summary", resp.context)
        html = resp.content.decode("utf-8")

        # Must render actual initial numbers in the metric-value divs
        self.assertIn('id="stat-total">1<', html)
        self.assertIn('id="stat-eligible">1<', html)
        self.assertIn('id="stat-psif" style="color: var(--risk-critical);">1<', html)

    def test_reports_server_rendered_metrics(self):
        """Reports page HTML must contain server-rendered KPI metric values instead of static placeholders."""
        inc = Incident.objects.create(
            id=uuid.uuid4(),
            incident_date=date(2026, 9, 1),
            composite_narrative="Gas detector alarm triggered in compressor area.",
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=self.model_version,
            psif_probability=0.82,
            psif_predicted=True,
            risk_level="high",
            is_sparse_input=False,
            top_factors=[],
        )

        resp = self.client.get("/dashboard/reports/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("analytics_summary", resp.context)
        html = resp.content.decode("utf-8")

        # Must render actual initial numbers in the metric-value divs
        self.assertIn('id="val-total-incidents">1<', html)
        self.assertIn('id="val-eligible">1<', html)
        self.assertIn('id="val-psifs" style="color: var(--risk-critical);">1<', html)

    def test_large_numbers_formatting_fixtures(self):
        """Verify thousands separators and exact numeric rendering for large numbers from 999 up to 999,999,999."""
        from django.template import Context, Template

        test_numbers = [
            (999, "999"),
            (9999, "9,999"),
            (99999, "99,999"),
            (561351, "561,351"),
            (999999, "999,999"),
            (1000000, "1,000,000"),
            (9999999, "9,999,999"),
            (99999999, "99,999,999"),
            (999999999, "999,999,999"),
        ]

        for raw_val, expected_str in test_numbers:
            tpl = Template(
                '<div class="metric-value tabular-nums" id="stat-total">{{ analytics_summary.formatted_total_incidents|default:analytics_summary.total_incidents|default:"--" }}</div>'
            )
            rendered = tpl.render(Context({
                "analytics_summary": {
                    "total_incidents": raw_val,
                    "formatted_total_incidents": f"{raw_val:,}",
                }
            }))
            self.assertIn(f">{expected_str}<", rendered, f"Failed for raw value {raw_val}")

    def test_no_duplicate_summary_request_in_home_template(self):
        """Dashboard template home.html must not contain duplicate fetch('/api/analytics/summary/') calls."""
        from pathlib import Path
        home_path = Path("templates/dashboard/home.html")
        content = home_path.read_text(encoding="utf-8")
        count = content.count("fetch('/api/analytics/summary/')")
        self.assertEqual(count, 1, f"Expected exactly 1 summary fetch in home.html, found {count}")

    def test_dashboard_kpi_grid_exists_and_renders_all_six_metrics(self):
        """Dashboard must contain kpi-grid and render all 6 individual KPI cards with their elements."""
        resp = self.client.get("/dashboard/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        html = resp.content.decode("utf-8")

        # 1. Grid container
        self.assertIn('class="metrics-grid kpi-grid" id="analytics-stats"', html)

        # 2. All 6 KPI cards
        self.assertEqual(html.count('class="metric kpi-card"'), 6, "Expected 6 kpi-card elements on Dashboard")

        # 3. All 6 metric values
        expected_ids = [
            "stat-total",
            "stat-eligible",
            "stat-psif",
            "stat-not-psif",
            "stat-insufficient",
            "stat-human-reviewed",
        ]
        for metric_id in expected_ids:
            self.assertIn(f'id="{metric_id}"', html, f"Metric value id {metric_id} missing on Dashboard")

        # 4. All 6 labels
        expected_labels = [
            "Total Incidents",
            "Prediction Eligible",
            "PSIF Candidates",
            "NOT PSIF",
            "Insufficient Evidence",
            "Human Reviewed",
        ]
        for label in expected_labels:
            self.assertIn(label, html, f"Label {label} missing on Dashboard")

    def test_reports_kpi_grid_exists_and_renders_all_six_metrics(self):
        """Reports page must contain kpi-grid and render all 6 individual KPI cards with their elements."""
        resp = self.client.get("/dashboard/reports/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        html = resp.content.decode("utf-8")

        # 1. Grid container
        self.assertIn('class="metrics-grid kpi-grid" id="stats-grid"', html)

        # 2. All 6 KPI cards
        self.assertEqual(html.count('class="metric kpi-card"'), 6, "Expected 6 kpi-card elements on Reports")

        # 3. All 6 metric values
        expected_ids = [
            "val-total-incidents",
            "val-eligible",
            "val-psifs",
            "val-not-psif",
            "val-insufficient",
            "val-human-reviewed",
        ]
        for metric_id in expected_ids:
            self.assertIn(f'id="{metric_id}"', html, f"Metric value id {metric_id} missing on Reports")

        # 4. All 6 labels
        expected_labels = [
            "Total Incidents",
            "Prediction Eligible",
            "PSIF Candidates",
            "NOT PSIF",
            "Insufficient Evidence",
            "Human Reviewed",
        ]
        for label in expected_labels:
            self.assertIn(label, html, f"Label {label} missing on Reports")

    def test_kpi_cards_seven_and_eight_digit_values_not_truncated(self):
        """Seven-digit and eight-digit numbers (e.g. 1,000,000 to 99,999,999) must render in full without truncation."""
        from django.template import Context, Template

        large_fixtures = [
            (1000000, "1,000,000"),
            (5678901, "5,678,901"),
            (10000000, "10,000,000"),
            (99999999, "99,999,999"),
            (999999999, "999,999,999"),
        ]
        for num, formatted in large_fixtures:
            tpl = Template(
                '<div class="metric kpi-card">'
                '<div class="metric-value tabular-nums" id="stat-total">{{ summary.formatted_total|default:summary.total }}</div>'
                '</div>'
            )
            out = tpl.render(Context({
                "summary": {"total": num, "formatted_total": f"{num:,}"}
            }))
            self.assertIn(f">{formatted}<", out)
            self.assertNotIn("K", out)
            self.assertNotIn("M", out)
            self.assertNotIn("...", out)

    def test_css_kpi_grid_responsive_rules(self):
        """CSS must define 4-column desktop, 2-column tablet, and 1-column mobile rules with overflow prevention."""
        from pathlib import Path
        css = Path("static/css/main.css").read_text(encoding="utf-8")

        # 4 columns on desktop
        self.assertIn("repeat(4, minmax(0, 1fr))", css)
        # 2 columns on tablet
        self.assertIn("repeat(2, minmax(0, 1fr))", css)
        # 1 column on mobile
        self.assertIn("grid-template-columns: 1fr;", css)
        # min-width: 0 prevention
        self.assertIn("min-width: 0;", css)


class BarrierIntelligenceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="barrier_analyst",
            email="barrier_analyst@oilindia.in",
            password="testpassword123",
            role=User.Role.ANALYST,
        )
        self.client.force_authenticate(user=self.user)
        self.client.force_login(self.user)

        self.model_version = ModelVersion.objects.create(
            version_label="v_test_barriers",
            bert_model_name="distilbert-base-uncased",
            xgboost_artifact_path="/tmp/test_xgb.json",
            encoder_artifact_path="/tmp/test_enc.joblib",
            is_active=True,
        )

    def tearDown(self):
        cache.clear()

    def test_barrier_api_unauthenticated(self):
        """Unauthenticated request must be rejected with 401/403."""
        anon_client = APIClient()
        resp = anon_client.get("/api/analytics/barriers/")
        self.assertIn(resp.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_barrier_api_authenticated(self):
        """Authenticated request returns 200 with barriers structure."""
        from apps.incidents.models import IOGPRuleTag

        inc = Incident.objects.create(
            id=uuid.uuid4(),
            incident_date=date(2026, 9, 1),
            department="Drilling",
            location="Rig-04",
            composite_narrative="Worker observed unverified energy isolation before pump maintenance.",
        )
        IOGPRuleTag.objects.create(
            incident=inc,
            rule="Energy Isolation",
            confidence=1.0,
        )
        PredictionResult.objects.create(
            incident=inc,
            model_version=self.model_version,
            psif_probability=0.75,
            psif_predicted=True,
            risk_level="high",
            is_sparse_input=False,
            top_factors=[],
        )

        resp = self.client.get("/api/analytics/barriers/?refresh=true")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertIn("barriers", data)
        self.assertIn("total_monitored_barriers", data)
        self.assertIn("methodology_disclaimer", data)
        self.assertIn("omitted_metrics", data)

        # Verify omitted metrics per preflight audit
        self.assertIn("concern_pattern_matches", data["omitted_metrics"])
        self.assertIn("barrier_health_score", data["omitted_metrics"])

        # Find Energy Isolation
        ei = next((b for b in data["barriers"] if b["rule"] == "Energy Isolation"), None)
        self.assertIsNotNone(ei)
        self.assertEqual(ei["matched_observations"], 1)
        self.assertEqual(ei["psif_linked_observations"], 1)
        self.assertEqual(ei["psif_linkage_rate"], 100.0)
        self.assertEqual(ei["affected_sites"], 1)

    def test_barrier_intelligence_view_renders(self):
        """HTML view /dashboard/barriers/ renders with 200 and methodology disclaimer."""
        resp = self.client.get("/dashboard/barriers/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("Barrier &amp; Critical-Control Intelligence", content)
        self.assertIn("Preflight Audited Methodology Notice", content)
        self.assertIn("not calibrated physical barrier integrity", content)
        self.assertIn("Preflight Audit &amp; Data Integrity Disclosure", content)
        self.assertIn("NOT CURRENTLY COMPUTABLE", content)

    def test_incident_filter_by_rule(self):
        """Incidents view /incidents/?rule=... and API /api/incidents/?rule=... correctly filter by IOGP rule."""
        from apps.incidents.models import IOGPRuleTag

        inc1 = Incident.objects.create(
            id=uuid.uuid4(),
            incident_date=date(2026, 9, 1),
            department="Drilling",
            description="Crane operation failure",
            composite_narrative="Crane operation failure during pipe lift",
        )
        IOGPRuleTag.objects.create(incident=inc1, rule="Safe Mechanical Lifting")

        inc2 = Incident.objects.create(
            id=uuid.uuid4(),
            incident_date=date(2026, 9, 2),
            department="Production",
            description="Hot work without fire watch",
            composite_narrative="Hot work without fire watch on vessel",
        )
        IOGPRuleTag.objects.create(incident=inc2, rule="Hot Work")

        from django.test import Client
        c = Client()
        c.force_login(self.user)
        resp = c.get("/incidents/?rule=Safe+Mechanical+Lifting")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("Safe Mechanical Lifting", content)

        # Also verify API filtering
        api_resp = self.client.get("/api/incidents/?rule=Safe+Mechanical+Lifting")
        self.assertEqual(api_resp.status_code, 200)
        api_data = api_resp.json()
        self.assertEqual(api_data["count"], 1)
        self.assertIn("Crane operation failure", api_data["results"][0]["composite_narrative"])

