"""
Regression tests for feature-integrity constraints.

These tests are PERMANENT GUARDS. They assert invariants that, if violated,
indicate a structural leakage regression in the ML training pipeline.

P0-1 (2026-09-05): severity_actual and severity_potential must NOT enter the
structured feature encoder. This was confirmed by repository audit: those
fields are module-level constants BOOLEAN_FIELDS, NUMERIC_FIELDS,
CATEGORICAL_FIELDS in ml_engine/feature_encoder.py — NOT class attributes
on StructuredFeatureEncoder itself.
"""


class TestStructuredEncoderLeakageGuards:
    """
    Verifies that the module-level encoder field lists in feature_encoder.py
    do NOT include any field that would constitute structural leakage of the
    heuristic PSIF label.

    Prohibited fields:
      - severity_actual      (heuristic label is partly derived from this)
      - severity_potential   (heuristic label is partly derived from this)
      - is_psif_human_label  (this IS the ground-truth target)
      - is_psif_heuristic_label (this IS the generated target)
      - psif_label_source    (this encodes which kind of label we have)
    """

    PROHIBITED_FIELDS = {
        "severity_actual",
        "severity_potential",
        "is_psif_human_label",
        "is_psif_heuristic_label",
        "psif_label_source",
        "adjudication_status",
        "adjudicated_human_decision",
        "adjudication_rationale",
        "adjudicated_by",
        "adjudicated_at",
        "reviewer_rationale",
    }

    def _get_all_encoder_fields(self):
        import ml_engine.feature_encoder as fe
        return (
            set(fe.BOOLEAN_FIELDS)
            | set(fe.NUMERIC_FIELDS)
            | set(fe.CATEGORICAL_FIELDS)
        )

    def test_severity_fields_not_in_structured_encoder(self):
        """Primary guard per specification P0-1."""
        import ml_engine.feature_encoder as fe
        leak_fields = {"severity_actual", "severity_potential"}
        encoded = set(fe.BOOLEAN_FIELDS) | set(fe.NUMERIC_FIELDS) | set(fe.CATEGORICAL_FIELDS)
        assert not (leak_fields & encoded), (
            "severity_actual/severity_potential entered the structured "
            "feature set — this reintroduces the leakage the trainer "
            "docstring was corrected to rule out."
        )

    def test_no_prohibited_field_in_any_encoder_list(self):
        """Omnibus guard covering all prohibited fields."""
        encoded = self._get_all_encoder_fields()
        intersection = self.PROHIBITED_FIELDS & encoded
        assert not intersection, (
            f"Prohibited fields entered the structured encoder: {intersection}. "
            "This is a structural leakage regression. Correct feature_encoder.py "
            "and update trainer.py documentation before retraining."
        )

    def test_boolean_fields_is_module_constant(self):
        """Confirms the module-level constant exists (structural sanity)."""
        import ml_engine.feature_encoder as fe
        assert hasattr(fe, "BOOLEAN_FIELDS"), "BOOLEAN_FIELDS not found in feature_encoder"
        assert hasattr(fe, "NUMERIC_FIELDS"), "NUMERIC_FIELDS not found in feature_encoder"
        assert hasattr(fe, "CATEGORICAL_FIELDS"), "CATEGORICAL_FIELDS not found in feature_encoder"
        assert isinstance(fe.BOOLEAN_FIELDS, list)
        assert isinstance(fe.NUMERIC_FIELDS, list)
        assert isinstance(fe.CATEGORICAL_FIELDS, list)

    def test_prepare_training_data_excludes_severity(self):
        """
        Static-analysis guard: prepare_training_data must not pass
        severity fields in the record dict without an explicit 'EXCLUDED'
        comment documenting the intentional absence.
        """
        import inspect
        from ml_engine.training import trainer as trainer_module

        source = inspect.getsource(trainer_module.prepare_training_data)
        excluded_comment_present = "EXCLUDED" in source

        # If severity field names appear in the dict construction, require
        # the EXCLUDED comment that documents their intentional absence.
        sev_actual_in_dict = ('"severity_actual"' in source)
        sev_potential_in_dict = ('"severity_potential"' in source)

        if sev_actual_in_dict and not excluded_comment_present:
            raise AssertionError(
                "prepare_training_data contains 'severity_actual' in the record dict "
                "without the expected EXCLUDED comment — confirm this is intentional."
            )
        if sev_potential_in_dict and not excluded_comment_present:
            raise AssertionError(
                "prepare_training_data contains 'severity_potential' in the record dict "
                "without the expected EXCLUDED comment — confirm this is intentional."
            )
