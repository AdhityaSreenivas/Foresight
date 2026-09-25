import json
import os
import random

import joblib
import numpy as np
import torch

from transformers import AutoTokenizer, AutoModel
from xgboost import XGBClassifier

from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    classification_report,
    confusion_matrix,
    roc_auc_score,
)


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_PATH = os.path.join(
    BASE_DIR,
    "data",
    "training_data.jsonl"
)
MODEL_DIR = os.path.join(
    BASE_DIR,
    "..",
    "..",
    "models_store"
)

MODEL_PATH = os.path.join(
    MODEL_DIR,
    "sif_classifier.joblib"
)

EMBEDDING_MODEL = "roberta-base"

MAX_LENGTH = 256
BATCH_SIZE = 16
RANDOM_STATE = 42


# ============================================================
# REPRODUCIBILITY
# ============================================================

random.seed(RANDOM_STATE)
np.random.seed(RANDOM_STATE)
torch.manual_seed(RANDOM_STATE)


# ============================================================
# LOAD JSONL DATASET
# ============================================================

def load_dataset():

    print("\nLoading dataset...")
    print(f"Dataset: {DATA_PATH}")

    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(
            f"\nDataset not found:\n{DATA_PATH}"
        )

    records = []

    with open(DATA_PATH, "r", encoding="utf-8") as file:

        for line_number, line in enumerate(file, start=1):

            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Invalid JSON on line {line_number}: {e}"
                )

            records.append(record)

    print(f"Records loaded: {len(records)}")

    return records


# ============================================================
# PREPARE TEXT + LABELS
# ============================================================

def prepare_data(records):

    texts = []
    labels = []

    for record in records:

        text = record.get("report_text")
        label = record.get("sif_label")

        if not text:
            continue

        if label not in [0, 1]:
            continue

        texts.append(text)
        labels.append(int(label))

    print(f"Valid records: {len(texts)}")

    print("\nClass distribution:")

    print(
        f"NON-SIF (0): {labels.count(0)}"
    )

    print(
        f"SIF (1):     {labels.count(1)}"
    )

    return texts, np.array(labels)


# ============================================================
# LOAD ROBERTA
# ============================================================

def load_roberta():

    print("\nLoading RoBERTa...")

    tokenizer = AutoTokenizer.from_pretrained(
        EMBEDDING_MODEL
    )

    model = AutoModel.from_pretrained(
        EMBEDDING_MODEL
    )

    device = torch.device(
        "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    model.to(device)

    model.eval()

    print(f"Device: {device}")

    return tokenizer, model, device


# ============================================================
# MEAN POOLING
# ============================================================

def mean_pooling(
    model_output,
    attention_mask
):

    token_embeddings = model_output.last_hidden_state

    mask = attention_mask.unsqueeze(-1)

    mask = mask.expand(
        token_embeddings.size()
    ).float()

    summed = torch.sum(
        token_embeddings * mask,
        dim=1
    )

    counts = torch.clamp(
        mask.sum(dim=1),
        min=1e-9
    )

    return summed / counts


# ============================================================
# CREATE ROBERTA EMBEDDINGS
# ============================================================

def create_embeddings(
    texts,
    tokenizer,
    model,
    device
):

    print("\nGenerating RoBERTa embeddings...")
    print(f"Total texts: {len(texts)}")

    embeddings = []

    for start in range(
        0,
        len(texts),
        BATCH_SIZE
    ):

        batch = texts[
            start:start + BATCH_SIZE
        ]

        encoded = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=MAX_LENGTH,
            return_tensors="pt"
        )

        encoded = {
            key: value.to(device)
            for key, value in encoded.items()
        }

        with torch.no_grad():

            output = model(
                **encoded
            )

            pooled = mean_pooling(
                output,
                encoded["attention_mask"]
            )

        batch_embeddings = (
            pooled
            .cpu()
            .numpy()
        )

        embeddings.append(
            batch_embeddings
        )

        completed = min(
            start + BATCH_SIZE,
            len(texts)
        )

        if (
            completed % 160 == 0
            or completed == len(texts)
        ):

            print(
                f"Embedded {completed}/{len(texts)}"
            )

    embeddings = np.vstack(
        embeddings
    )

    print(
        f"\nEmbedding shape: {embeddings.shape}"
    )

    return embeddings


# ============================================================
# TRAIN XGBOOST
# ============================================================

def train_classifier(X_train, y_train):

    print("\nTraining XGBoost classifier...")

    # Force a clean contiguous float32 matrix.
    X_train = np.ascontiguousarray(X_train, dtype=np.float32)
    y_train = np.asarray(y_train, dtype=np.int32)

    print(f"X_train shape: {X_train.shape}")
    print(f"X_train dtype: {X_train.dtype}")
    print(f"y_train shape: {y_train.shape}")
    print(f"y_train dtype: {y_train.dtype}")

    model = XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=RANDOM_STATE,
        n_jobs=1,
        tree_method="hist",
        verbosity=2
    )

    print("Starting XGBoost fit...")

    model.fit(
        X_train,
        y_train
    )

    print("XGBoost training completed.")

    return model

# ============================================================
# EVALUATE MODEL
# ============================================================

def evaluate_model(
    model,
    X_test,
    y_test
):

    print("\n")
    print("=" * 60)
    print("MODEL EVALUATION")
    print("=" * 60)

    predictions = model.predict(
        X_test
    )

    probabilities = model.predict_proba(
        X_test
    )[:, 1]

    accuracy = accuracy_score(
        y_test,
        predictions
    )

    precision = precision_score(
        y_test,
        predictions,
        zero_division=0
    )

    recall = recall_score(
        y_test,
        predictions,
        zero_division=0
    )

    f1 = f1_score(
        y_test,
        predictions,
        zero_division=0
    )

    auc = roc_auc_score(
        y_test,
        probabilities
    )

    print(
        f"\nAccuracy : {accuracy:.4f}"
    )

    print(
        f"Precision: {precision:.4f}"
    )

    print(
        f"Recall   : {recall:.4f}"
    )

    print(
        f"F1 Score : {f1:.4f}"
    )

    print(
        f"ROC-AUC  : {auc:.4f}"
    )

    print("\nClassification Report:")

    print(
        classification_report(
            y_test,
            predictions,
            target_names=[
                "NON-SIF",
                "SIF"
            ],
            zero_division=0
        )
    )

    print("Confusion Matrix:")

    print(
        confusion_matrix(
            y_test,
            predictions
        )
    )

    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "roc_auc": auc
    }


# ============================================================
# SAVE MODEL
# ============================================================

def save_model(
    model,
    metrics
):

    os.makedirs(
        MODEL_DIR,
        exist_ok=True
    )

    model_package = {

        "model": model,

        "embedding_model":
            EMBEDDING_MODEL,

        "max_length":
            MAX_LENGTH,

        "threshold":
            0.50,

        "metrics":
            metrics,

        "label_mapping": {

            0: "NON-SIF",

            1: "SIF-POTENTIAL"

        }

    }

    joblib.dump(
        model_package,
        MODEL_PATH
    )

    print("\n")
    print("=" * 60)

    print(
        f"MODEL SAVED:\n{MODEL_PATH}"
    )

    print("=" * 60)


# ============================================================
# MAIN
# ============================================================

def main():

    print("\n")
    print("=" * 60)
    print("SIF PRECURSOR MODEL TRAINING")
    print("=" * 60)

    # 1. Load dataset
    records = load_dataset()

    # 2. Prepare text and labels
    texts, labels = prepare_data(
        records
    )

    # 3. Split dataset
    print("\nSplitting dataset...")

    X_train_text, X_temp_text, y_train, y_temp = train_test_split(

        texts,
        labels,

        test_size=0.30,

        random_state=RANDOM_STATE,

        stratify=labels
    )

    X_val_text, X_test_text, y_val, y_test = train_test_split(

        X_temp_text,
        y_temp,

        test_size=0.50,

        random_state=RANDOM_STATE,

        stratify=y_temp
    )

    print(
        f"Training samples:   {len(X_train_text)}"
    )

    print(
        f"Validation samples: {len(X_val_text)}"
    )

    print(
        f"Testing samples:    {len(X_test_text)}"
    )

    # 4. Load RoBERTa
    tokenizer, roberta, device = load_roberta()

    # 5. Generate embeddings
    X_train = create_embeddings(
        X_train_text,
        tokenizer,
        roberta,
        device
    )

    X_val = create_embeddings(
        X_val_text,
        tokenizer,
        roberta,
        device
    )

    X_test = create_embeddings(
        X_test_text,
        tokenizer,
        roberta,
        device
    )

    # 6. Train XGBoost
    classifier = train_classifier(
        X_train,
        y_train
    )

    # 7. Evaluate on validation set
    print("\nValidation performance:")

    evaluate_model(
        classifier,
        X_val,
        y_val
    )

    # 8. Final evaluation on test set
    print("\nFinal test performance:")

    metrics = evaluate_model(
        classifier,
        X_test,
        y_test
    )

    # 9. Save model
    save_model(
        classifier,
        metrics
    )

    print("\nTraining finished successfully.")


if __name__ == "__main__":
    main()