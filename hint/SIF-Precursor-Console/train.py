import json
from pathlib import Path
import os
import joblib
import numpy as np

from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix

from xgboost import XGBClassifier

from core.ml.embed import get_embedding


# ============================================================
# PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

DATASET_PATH = (
    PROJECT_ROOT
    / "core"
    / "ml"
    / "data"
    / "training_data.jsonl"
)

MODEL_DIR = PROJECT_ROOT / "models_store"

MODEL_DIR.mkdir(
    exist_ok=True
)

MODEL_PATH = (
    MODEL_DIR
    / "sif_classifier.joblib"
)


# ============================================================
# LOAD DATASET
# ============================================================

print("=" * 60)
print("SIF PRECURSOR MODEL TRAINING")
print("=" * 60)

print("\nLoading dataset...")

with open(
    DATASET_PATH,
    "r",
    encoding="utf-8"
) as file:

    data = []

    for line in file:
        line = line.strip()

        if line:
            data.append(json.loads(line))

print(
    f"Total records: {len(data)}"
)


# ============================================================
# EXTRACT TEXT AND LABEL
# ============================================================

texts = []
labels = []

for item in data:

    text = item.get(
        "report_text",
        ""
    ).strip()

    label = item.get(
        "sif_label"
    )

    if not text:
        continue

    if label not in [0, 1]:
        continue

    texts.append(text)
    labels.append(label)


print(
    f"Valid records: {len(texts)}"
)


# ============================================================
# CHECK DATA BALANCE
# ============================================================

sif_count = sum(labels)

non_sif_count = len(labels) - sif_count

print("\nClass distribution:")

print(
    f"NON-SIF: {non_sif_count}"
)

print(
    f"SIF:     {sif_count}"
)


# ============================================================
# GENERATE ROBERTA EMBEDDINGS
# ============================================================

print("\nGenerating RoBERTa embeddings...")
print("This may take some time.\n")

embeddings = []

for index, text in enumerate(texts):

    embedding = get_embedding(text)

    embeddings.append(embedding)

    if (index + 1) % 100 == 0:
        print(f"Processed {index + 1}/{len(texts)}")

X = np.array(embeddings)

y = np.array(
    labels
)


print("\nEmbedding matrix:")

print(
    X.shape
)


# ============================================================
# TRAIN / VALIDATION / TEST SPLIT
# ============================================================

X_train, X_temp, y_train, y_temp = train_test_split(
    X,
    y,
    test_size=0.30,
    random_state=42,
    stratify=y
)

X_val, X_test, y_val, y_test = train_test_split(
    X_temp,
    y_temp,
    test_size=0.50,
    random_state=42,
    stratify=y_temp
)


print("\nDataset split:")

print(
    f"Training:   {len(X_train)}"
)

print(
    f"Validation: {len(X_val)}"
)

print(
    f"Testing:    {len(X_test)}"
)


# ============================================================
# TRAIN XGBOOST
# ============================================================

print("\nTraining XGBoost...")


model = XGBClassifier(

    n_estimators=300,

    max_depth=5,

    learning_rate=0.05,

    subsample=0.8,

    colsample_bytree=0.8,

    objective="binary:logistic",

    eval_metric="logloss",

    random_state=42,

    n_jobs=1
)


model.fit(
    X_train,
    y_train
)


# ============================================================
# VALIDATION
# ============================================================

print("\n" + "=" * 60)

print("VALIDATION RESULTS")

print("=" * 60)


val_predictions = model.predict(
    X_val
)

print(
    classification_report(
        y_val,
        val_predictions,
        target_names=[
            "NON-SIF",
            "SIF"
        ]
    )
)


# ============================================================
# FINAL TEST
# ============================================================

print("\n" + "=" * 60)

print("FINAL TEST RESULTS")

print("=" * 60)


test_predictions = model.predict(
    X_test
)


print(
    classification_report(
        y_test,
        test_predictions,
        target_names=[
            "NON-SIF",
            "SIF"
        ]
    )
)


# ============================================================
# CONFUSION MATRIX
# ============================================================

print("\nConfusion Matrix:")

print(
    confusion_matrix(
        y_test,
        test_predictions
    )
)


# ============================================================
# SAVE MODEL
# ============================================================

joblib.dump(
    model,
    MODEL_PATH
)


print("\n" + "=" * 60)

print("TRAINING COMPLETE")

print("=" * 60)

print(
    f"\nModel saved to:\n{MODEL_PATH}"
)
