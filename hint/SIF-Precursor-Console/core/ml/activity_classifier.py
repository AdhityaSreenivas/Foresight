import joblib
import numpy as np
from pathlib import Path
from core.ml.embed import get_embedding

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = PROJECT_ROOT / "models_store" / "activity_classifier.joblib"

_activity_model_cache = None

def get_activity_model():
    global _activity_model_cache
    if _activity_model_cache is None:
        if MODEL_PATH.exists():
            try:
                _activity_model_cache = joblib.load(MODEL_PATH)
            except Exception as e:
                print(f"Error loading Activity classifier model: {e}")
                _activity_model_cache = None
    return _activity_model_cache

def predict_activity(text=None, embedding=None, confidence_threshold=0.20):
    """
    Predicts Activity from RoBERTa embedding or text using 16 original dataset classes.
    """
    artifact = get_activity_model()
    
    if artifact is not None and isinstance(artifact, dict) and "model" in artifact:
        model = artifact["model"]
        label_encoder = artifact["label_encoder"]
        classes = list(label_encoder.classes_)
        
        if embedding is None and text:
            embedding = get_embedding(text)
            
        if embedding is not None:
            X = np.array([embedding])
            probs = model.predict_proba(X)[0]
            top_idx = int(np.argmax(probs))
            top_prob = float(probs[top_idx])
            top_class = str(label_encoder.inverse_transform([top_idx])[0])
            
            all_probs = {c: float(p) for c, p in zip(classes, probs)}
            
            if top_prob >= confidence_threshold:
                return {
                    "activity": top_class,
                    "activity_probability": round(top_prob, 4),
                    "activity_all_probabilities": all_probs,
                    "source": "ml"
                }
    
    return {
        "activity": "General Operations",
        "activity_probability": 0.0,
        "activity_all_probabilities": {},
        "source": "default"
    }
