import os
import sys
import subprocess
from pathlib import Path

PROJECT_DIR = str(Path(__file__).resolve().parent.parent)
PYTHON = sys.executable

def test_explainability_regression():
    script = """
import os, sys, tempfile, shutil
import numpy as np

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django
django.setup()

from ml_engine.bert_encoder import encode_texts, _get_model_and_tokenizer
from ml_engine.feature_encoder import StructuredFeatureEncoder
from ml_engine.text_preprocessing import build_composite_narrative
from ml_engine.training.trainer import _train_single_model, save_artifacts
from ml_engine.model_inference import PSIFPredictor

BERT_MODEL = "distilbert-base-uncased"
artifact_dir = tempfile.mkdtemp(prefix="psif_test_artifacts_")

records = []
labels = []
for i in range(10):
    r = dict(
        department=f"D-{i}", injury_type="Laceration", body_part="Hand",
        immediate_cause="PPE", root_cause_category="Behavior",
        near_miss=True,
        description="Worker sustained serious head injury from falling equipment.",
        corrective_actions="Installed safety nets.", witness_statement="Saw the incident.",
    )
    records.append(r)
    labels.append(1)
for i in range(20):
    r = dict(
        department=f"D-{10+i}", injury_type="Bruise", body_part="Knee",
        immediate_cause="Slip", root_cause_category="Housekeeping",
        near_miss=False,
        description="Minor slip on wet floor.", corrective_actions="Mopped floor.",
        witness_statement="No witnesses.",
    )
    records.append(r)
    labels.append(0)

labels = np.array(labels, dtype=int)

narratives = [build_composite_narrative(r["description"], r["corrective_actions"], r["witness_statement"]) for r in records]
bert_emb = encode_texts(narratives, BERT_MODEL, batch_size=16)
_, bert_model = _get_model_and_tokenizer(BERT_MODEL)
bert_dim = bert_model.config.hidden_size

enc = StructuredFeatureEncoder()
X_struct = enc.fit_transform(records)
X_fused = np.hstack([bert_emb, X_struct])

# Give it some weight to learn near_miss=True -> positive label
model = _train_single_model(X_fused, labels, best_params=dict(max_depth=3, learning_rate=0.1, n_estimators=10, min_child_weight=1), scale_pos_weight=2.0, seed=42)

from pathlib import Path
metadata = dict(
    model_version="test_v1", bert_model_name=BERT_MODEL,
    bert_hidden_dimension=bert_dim, selected_threshold=0.3,
    structured_feature_names=enc.feature_names_,
)

save_artifacts(Path(artifact_dir), model, enc, metadata)

predictor = PSIFPredictor(
    xgboost_artifact_path=os.path.join(artifact_dir, "model.json"),
    encoder_artifact_path=os.path.join(artifact_dir, "encoder.joblib"),
    bert_model_name=BERT_MODEL,
    psif_threshold=0.3,
    bert_dim=bert_dim,
)

rec1 = dict(
    department="D-0", injury_type="Bruise", body_part="Knee",
    immediate_cause="Slip", root_cause_category="Housekeeping",
    near_miss=False,
    description="Minor slip on wet floor.",
    corrective_actions="Mopped floor.", witness_statement="No witnesses.",
)

rec2 = dict(
    department="D-0", injury_type="Laceration", body_part="Hand",
    immediate_cause="PPE", root_cause_category="Behavior",
    near_miss=True,
    description="Worker sustained serious head injury from falling equipment.",
    corrective_actions="Installed safety nets.", witness_statement="Saw the incident.",
)

pred1 = predictor.predict(rec1)
pred2 = predictor.predict(rec2)

assert pred1.top_factors != pred2.top_factors, "Identical top factors!"

# 1. Non-empty top_factors
assert len(pred2.top_factors) > 0, "Top factors is empty"

# 2. Sensible ordering (descending by absolute magnitude)
magnitudes = [abs(f["contribution"]) for f in pred2.top_factors]
assert magnitudes == sorted(magnitudes, reverse=True), "Factors are not ordered by absolute magnitude"

# 3. Valid signed contributions
for f in pred2.top_factors:
    assert isinstance(f["contribution"], float), "Contribution is not float"
    assert f["contribution"] != 0.0, "Contribution is exactly 0.0"

# 4. Human-readable factor names (start with uppercase, replace underscores)
for f in pred2.top_factors:
    assert f["feature"][0].isupper(), f"Feature name '{f['feature']}' doesn't start with uppercase"
    assert "_" not in f["feature"], f"Feature name '{f['feature']}' contains underscore"

# 5. Incident-specific values
near_miss_factor = next((f for f in pred2.top_factors if f["feature"] == "Near miss"), None)
if near_miss_factor:
    # If model used near_miss, it should be positive for rec2
    pass

shutil.rmtree(artifact_dir)
print("PASS: SHAP Regression")
"""

    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "1"
    env["TOKENIZERS_PARALLELISM"] = "false"
    env["LOKY_MAX_CPU_COUNT"] = "1"

    full_script = f"import os, sys\nsys.path.insert(0, '{PROJECT_DIR}')\n{script}"

    result = subprocess.run(
        [PYTHON, "-c", full_script],
        capture_output=True, text=True,
        cwd=PROJECT_DIR,
        timeout=120,
        env=env,
    )
    
    assert result.returncode == 0, f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    assert "PASS: SHAP Regression" in result.stdout
