import joblib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

MODEL_PATH = (
    PROJECT_ROOT
    / "models_store"
    / "sif_classifier.joblib"
)

print("Starting model load...")
print("Model path:", MODEL_PATH)
print("File exists:", MODEL_PATH.exists())

model = joblib.load(MODEL_PATH)

print("MODEL LOADED SUCCESSFULLY")
print(type(model))
