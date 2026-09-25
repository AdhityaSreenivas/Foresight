import numpy as np
import xgboost as xgb
from unittest import mock
from django.test import TestCase

from ml_engine.model_inference import _format_feature_name, _compute_shap_top_factors


class ExplainabilityTests(TestCase):

    def test_format_feature_name(self):
        """Test the transformation of machine feature names to human-readable strings."""
        self.assertEqual(_format_feature_name("near_miss"), "Near miss")
        
        # Test Severity Potential
        self.assertEqual(_format_feature_name("severity_potential=serious"), "Serious potential severity")
        self.assertEqual(_format_feature_name("severity_potential=fatality"), "Fatality potential severity")
        
        # Test Severity Actual
        self.assertEqual(_format_feature_name("severity_actual=first_aid"), "First-aid actual severity")
        self.assertEqual(_format_feature_name("severity_actual=none"), "None actual severity")
        
        # Test Categorical
        self.assertEqual(_format_feature_name("department=Maintenance"), "Maintenance department")
        self.assertEqual(_format_feature_name("injury_type=laceration"), "Laceration injury")
        self.assertEqual(_format_feature_name("body_part=hand"), "Hand (body part)")
        self.assertEqual(_format_feature_name("immediate_cause=equipment_failure"), "Equipment failure (immediate cause)")
        self.assertEqual(_format_feature_name("root_cause_category=lack_of_training"), "Lack of training (root cause)")
        
        # Test fallback
        self.assertEqual(_format_feature_name("unknown_feature"), "Unknown feature")

    @mock.patch("shap.TreeExplainer")
    def test_compute_shap_top_factors(self, mock_tree_explainer):
        """Test SHAP computation logic with mocked TreeExplainer."""
        # Create a mock explainer and shap values
        mock_explainer = mock.Mock()
        mock_tree_explainer.return_value = mock_explainer
        
        # 2 BERT dims, 3 structured features (5 total)
        bert_dim = 2
        fused_vector = np.array([0.1, 0.2, 1.0, 0.0, 1.0])
        
        # Let's say shap returns an array of shape (1, 5)
        # Class 1 shap values
        mock_explainer.shap_values.return_value = [
            np.zeros((1, 5)), 
            np.array([[0.05, -0.01, 0.2, -0.05, 0.0001]])
        ]
        
        feature_names = ["bert_0", "bert_1", "department=Operations", "near_miss", "severity_actual=first_aid"]
        
        # Mock booster
        mock_booster = mock.Mock(spec=xgb.Booster)
        
        factors = _compute_shap_top_factors(
            booster=mock_booster,
            fused_vector=fused_vector,
            feature_names=feature_names,
            psif_predicted=True,
            bert_dim=bert_dim,
            top_n=3,
            min_abs_contribution=0.001
        )
        
        # BERT total: 0.05 + -0.01 = 0.04
        # Structured: 
        #   department=Operations -> Operations department: 0.2
        #   near_miss -> Near miss: -0.05
        #   severity_actual=first_aid -> First-aid actual severity: 0.0001 (should be filtered out < 0.001)
        
        self.assertEqual(len(factors), 2)
        
        # 1st factor: Operations department (0.2)
        self.assertEqual(factors[0]["feature"], "Operations department")
        self.assertAlmostEqual(factors[0]["contribution"], 0.2)
        
        # 2nd factor: Narrative content (0.04)
        self.assertEqual(factors[1]["feature"], "Narrative content")
        self.assertAlmostEqual(factors[1]["contribution"], 0.04)

    @mock.patch("shap.TreeExplainer")
    def test_regression_gates(self, mock_tree_explainer):
        """Test Gates 21-24: Empty, Whitespace, Populated, SHAP Category"""
        mock_explainer = mock.Mock()
        mock_tree_explainer.return_value = mock_explainer
        
        # 1 BERT dim, 1 structured feature
        bert_dim = 1
        feature_names = ["bert_0", "department=Operations"]
        mock_booster = mock.Mock(spec=xgb.Booster)
        
        # Test 1: psif_predicted=False (empty/whitespace scenario, negative contrib)
        mock_explainer.shap_values.return_value = [np.zeros((1, 2)), np.array([[-0.5, -0.2]])]
        fused_vector = np.array([0.0, 1.0])
        factors_neg = _compute_shap_top_factors(
            booster=mock_booster, fused_vector=fused_vector, feature_names=feature_names,
            psif_predicted=False, bert_dim=bert_dim, top_n=5, min_abs_contribution=0.001
        )
        self.assertEqual(len(factors_neg), 2)
        self.assertEqual(factors_neg[0]["feature"], "Narrative content")
        self.assertEqual(factors_neg[1]["feature"], "Operations department")
        
        # Test 2: Categorical missing/omitted
        mock_explainer.shap_values.return_value = [np.zeros((1, 2)), np.array([[0.5, 0.2]])]
        fused_vector_missing = np.array([0.0, 0.0]) # operations not selected
        factors_missing = _compute_shap_top_factors(
            booster=mock_booster, fused_vector=fused_vector_missing, feature_names=feature_names,
            psif_predicted=True, bert_dim=bert_dim, top_n=5, min_abs_contribution=0.001
        )
        self.assertEqual(len(factors_missing), 1)
        # Operations department is omitted because val == 0.0 (Ghost attribute eliminated)
        self.assertEqual(factors_missing[0]["feature"], "Narrative content")
