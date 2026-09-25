import joblib
import numpy as np
from pathlib import Path
from core.ml.embed import get_embedding
from core.ml.lsr import map_life_saving_rule

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = PROJECT_ROOT / "models_store" / "lsr_classifier.joblib"

_lsr_model_cache = None

def get_lsr_model():
    global _lsr_model_cache
    if _lsr_model_cache is None:
        if MODEL_PATH.exists():
            try:
                _lsr_model_cache = joblib.load(MODEL_PATH)
            except Exception as e:
                print(f"Error loading LSR classifier model: {e}")
                _lsr_model_cache = None
    return _lsr_model_cache

def predict_lsr(text=None, embedding=None, confidence_threshold=0.50):
    """
    Predicts Life-Saving Rule (LSR) category from RoBERTa embedding or text.
    Falls back to keyword matching if ML model is unavailable or confidence is low.
    If no relevant safety keywords exist and ML confidence is low, returns 'Unclassified'.
    """
    artifact = get_lsr_model()
    kw_result = map_life_saving_rule(text or "")
    kw_rule = kw_result.get("rule", "Unclassified")
    kw_score = kw_result.get("score", 0)
    
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
            
            # Accept ML prediction if high confidence (>= 0.50) OR if top ML prediction aligns with keyword match
            if top_prob >= confidence_threshold or (top_class == kw_rule and kw_score > 0):
                return {
                    "life_saving_rule": top_class,
                    "lsr_probability": round(top_prob, 4),
                    "lsr_all_probabilities": all_probs,
                    "source": "ml"
                }
    
    # Fallback to keyword matching
    if kw_rule != "Unclassified" and kw_score > 0:
        return {
            "life_saving_rule": kw_rule,
            "lsr_probability": 0.50,
            "lsr_all_probabilities": {},
            "source": "keyword"
        }
        
    return {
        "life_saving_rule": "Unclassified",
        "lsr_probability": 0.0,
        "lsr_all_probabilities": {},
        "source": "keyword"
    }
