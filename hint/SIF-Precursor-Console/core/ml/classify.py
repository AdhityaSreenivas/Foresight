import joblib
import numpy as np
from pathlib import Path

from core.ml.embed import get_embedding


PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODEL_PATH = (
    PROJECT_ROOT
    / "models_store"
    / "sif_classifier.joblib"
)

loaded_obj = joblib.load(MODEL_PATH)
if isinstance(loaded_obj, dict) and "model" in loaded_obj:
    model = loaded_obj["model"]
else:
    model = loaded_obj


def classify_report(text, embedding=None):
    if embedding is None:
        embedding = get_embedding(text)
    X = np.array([embedding])
    probabilities = model.predict_proba(X)[0]
    prediction = int(model.predict(X)[0])

    if prediction == 1:
        classification = "SIF-POTENTIAL"
        confidence = float(probabilities[1])
    else:
        classification = "NON-SIF"
        confidence = float(probabilities[0])

    return {
        "classification": classification,
        "is_sif": bool(prediction == 1),
        "confidence": confidence,
        "sif_probability": float(probabilities[1]),
        "non_sif_probability": float(probabilities[0])
    }
