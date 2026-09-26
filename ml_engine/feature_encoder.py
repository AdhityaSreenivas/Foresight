"""
PSIF Platform — Structured Feature Encoder

Encodes the categorical, boolean, and numeric structured fields from an
Incident record into a fixed-size numeric vector for concatenation with
the BERT embedding.

Design:
  - Categorical fields → OneHotEncoder (scikit-learn)
    Fitted on the training set.  Unknown categories at inference time are
    handled via handle_unknown='ignore' (zero-vector for unseen category).
  - Numeric fields → StandardScaler (zero mean, unit variance)
    Fitted on the training set.
  - Boolean fields → 0/1 integer directly (no scaling needed).
  - Missing values:
      categorical → imputed with the sentinel string "_MISSING_"
      numeric     → imputed with the training-set median

The fitted encoder objects are persisted to disk via joblib so that
inference always uses identical encoding to training.  Loading the fitted
encoder is the job of model_inference.py.

Feature vector layout (fixed order, must not change between training and
inference):
  [bool_features | scaled_numeric | one_hot_categorical]

The feature list is recorded in ModelVersion.metrics["feature_list"].
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd

try:
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    HAS_SKLEARN = True
except ImportError:
    OneHotEncoder = None
    StandardScaler = None
    SimpleImputer = None
    Pipeline = None
    HAS_SKLEARN = False

logger = logging.getLogger(__name__)

# ── Canonical field lists ──────────────────────────────────────────────────────
# These lists define the EXACT features used by the model.
# Adding, removing, or reordering fields here requires retraining.

BOOLEAN_FIELDS: list[str] = [
    "near_miss",
]

NUMERIC_FIELDS: list[str] = [
    # Currently none in the core schema — placeholder for future numeric
    # features (e.g., days_since_last_incident, employee_count).
]

CATEGORICAL_FIELDS: list[str] = [
    "department",
    "injury_type",
    "body_part",
    "immediate_cause",
    "root_cause_category",
]

# Sentinel value for missing categoricals
MISSING_SENTINEL = "_MISSING_"


def _incident_to_series(record: dict) -> pd.Series:
    """Convert a raw incident record dict to a pandas Series with canonical fields."""
    return pd.Series({field: record.get(field) for field in
                      BOOLEAN_FIELDS + NUMERIC_FIELDS + CATEGORICAL_FIELDS})


class StructuredFeatureEncoder:
    """
    Encodes structured incident fields into a 1D numpy array for XGBoost input.

    Usage:
        # Training
        encoder = StructuredFeatureEncoder()
        X_structured = encoder.fit_transform(records)  # list of dicts
        encoder.save(path)

        # Inference
        encoder = StructuredFeatureEncoder.load(path)
        x = encoder.transform_single(record)  # single dict → 1D array
    """

    def __init__(self) -> None:
        self._bool_fields = BOOLEAN_FIELDS
        self._numeric_fields = NUMERIC_FIELDS
        self._categorical_fields = CATEGORICAL_FIELDS

        # Scikit-learn pipeline for categoricals:
        #   impute missing → one-hot encode (unknown → zero vector)
        self._cat_pipeline: Optional[Pipeline] = None

        # Pipeline for numerics: impute median → standard scale
        self._num_pipeline: Optional[Pipeline] = None

        self.is_fitted = False
        self.feature_names_: list[str] = []

    def _make_dataframe(self, records: list[dict]) -> pd.DataFrame:
        """Convert a list of incident record dicts into a DataFrame."""
        rows = []
        for rec in records:
            row = {}
            for f in self._bool_fields:
                val = rec.get(f)
                row[f] = 1 if val is True else (0 if val is False else 0)
            for f in self._numeric_fields:
                row[f] = rec.get(f)
            for f in self._categorical_fields:
                val = rec.get(f)
                row[f] = str(val) if val is not None else MISSING_SENTINEL
            rows.append(row)
        return pd.DataFrame(rows)

    def fit_transform(self, records: list[dict]) -> np.ndarray:
        """Fit the encoder on training records and return the encoded matrix."""
        df = self._make_dataframe(records)

        parts = []
        feature_names = []

        # Booleans (already 0/1, no pipeline needed)
        if self._bool_fields:
            bool_arr = df[self._bool_fields].values.astype(float)
            parts.append(bool_arr)
            feature_names.extend(self._bool_fields)

        # Numerics
        if self._numeric_fields:
            self._num_pipeline = Pipeline([
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
            ])
            num_arr = self._num_pipeline.fit_transform(df[self._numeric_fields])
            parts.append(num_arr)
            feature_names.extend(self._numeric_fields)

        # Categoricals
        if self._categorical_fields:
            # Fill NaN with sentinel before encoding
            cat_df = df[self._categorical_fields].fillna(MISSING_SENTINEL)
            self._cat_pipeline = Pipeline([
                ("encoder", OneHotEncoder(
                    handle_unknown="ignore",
                    sparse_output=False,
                    dtype=float,
                )),
            ])
            cat_arr = self._cat_pipeline.fit_transform(cat_df)
            enc: OneHotEncoder = self._cat_pipeline.named_steps["encoder"]
            for field, categories in zip(self._categorical_fields, enc.categories_):
                for cat in categories:
                    feature_names.append(f"{field}={cat}")
            parts.append(cat_arr)

        self.feature_names_ = feature_names
        self.is_fitted = True

        result = np.hstack(parts) if parts else np.empty((len(records), 0))
        logger.info("StructuredFeatureEncoder fitted: %d features, %d records",
                    len(self.feature_names_), len(records))
        return result

    def transform(self, records: list[dict]) -> np.ndarray:
        """Transform a list of records using the fitted encoder."""
        if not self.is_fitted:
            raise RuntimeError("Encoder must be fitted before calling transform().")

        df = self._make_dataframe(records)
        parts = []

        if self._bool_fields:
            parts.append(df[self._bool_fields].values.astype(float))

        if self._numeric_fields and self._num_pipeline:
            parts.append(self._num_pipeline.transform(df[self._numeric_fields]))

        if self._categorical_fields and self._cat_pipeline:
            cat_df = df[self._categorical_fields].fillna(MISSING_SENTINEL)
            parts.append(self._cat_pipeline.transform(cat_df))

        return np.hstack(parts) if parts else np.empty((len(records), 0))

    def transform_single(self, record: dict) -> np.ndarray:
        """Transform a single incident record dict → 1D numpy array."""
        return self.transform([record])[0]

    def save(self, path: str | Path) -> None:
        """Persist the fitted encoder to disk."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        logger.info("StructuredFeatureEncoder saved to %s", path)

    @classmethod
    def load(cls, path: str | Path) -> "StructuredFeatureEncoder":
        """Load a previously saved encoder from disk."""
        path = Path(path)
        encoder = joblib.load(path)
        logger.info("StructuredFeatureEncoder loaded from %s", path)
        return encoder
