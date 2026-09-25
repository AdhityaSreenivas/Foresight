import os
import sys
import json
import argparse
from pathlib import Path
from collections import Counter

os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import numpy as np
import joblib

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = PROJECT_ROOT / "core" / "ml" / "data" / "training_data.jsonl"
MODELS_DIR = PROJECT_ROOT / "models_store"
CACHE_DIR = MODELS_DIR / "embeddings"

EMBEDDING_MODEL = "roberta-base"
MAX_LENGTH = 512
BATCH_SIZE = 32
RANDOM_STATE = 42

def load_dataset():
    print(f"Loading dataset from: {DATA_PATH}")
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Dataset not found at {DATA_PATH}")
    records = []
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    print(f"Total dataset records loaded: {len(records)}")
    return records


def print_dataset_statistics(records):
    print("\n" + "=" * 60)
    print("DATASET VALIDATION & STATISTICS")
    print("=" * 60)
    print(f"Total Records: {len(records)}")
    sif_counts = Counter(r.get("sif_label") for r in records)
    print(f"SIF Label Counts: {dict(sif_counts)}")
    lsr_counts = Counter(r.get("life_saving_rule") for r in records)
    print("\nLife-Saving Rule Counts (All):")
    for lsr, count in lsr_counts.most_common():
        print(f"  {lsr}: {count}")
    usable_lsr_records = [
        r for r in records
        if r.get("sif_label") == 1
        and r.get("life_saving_rule") not in ["Unclassified", "N/A"]
    ]
    print(f"\nUsable SIF LSR Records: {len(usable_lsr_records)}")
    usable_lsr_counts = Counter(r.get("life_saving_rule") for r in usable_lsr_records)
    print("Usable LSR Classes and Counts (8 valid classes expected):")
    for lsr, count in sorted(usable_lsr_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {lsr}: {count}")
    act_counts = Counter(r.get("activity") for r in records)
    print(f"\nActivity Counts (Total Classes = {len(act_counts)}):")
    for act, count in act_counts.most_common():
        print(f"  {act}: {count}")
    print("=" * 60 + "\n")

def generate_and_cache_embeddings(records):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    embeddings_file = CACHE_DIR / "all_embeddings.npy"
    metadata_file = CACHE_DIR / "embeddings_metadata.json"
    if embeddings_file.exists() and metadata_file.exists():
        try:
            with open(metadata_file, "r") as f:
                meta = json.load(f)
            cached_arr = np.load(embeddings_file)
            if meta.get("num_records") == len(records) and meta.get("embedding_dim") == 768 and cached_arr.shape == (len(records), 768):
                print(f"Valid cached embeddings found at {embeddings_file} with shape {cached_arr.shape}. Reusing cache.")
                return cached_arr
            else:
                print("Cache mismatch detected. Regenerating embeddings...")
        except Exception as e:
            print(f"Cache loading failed ({e}). Regenerating embeddings...")

    print("\nGenerating RoBERTa embeddings for all dataset records...")
    import torch
    from transformers import AutoTokenizer, AutoModel
    tokenizer = AutoTokenizer.from_pretrained(EMBEDDING_MODEL)
    model = AutoModel.from_pretrained(EMBEDDING_MODEL)
    model.eval()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    texts = [r.get("report_text", "") for r in records]
    embeddings_list = []

    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start:start + BATCH_SIZE]
        encoded = tokenizer(batch, padding=True, truncation=True, max_length=MAX_LENGTH, return_tensors="pt")
        encoded = {k: v.to(device) for k, v in encoded.items()}
        with torch.no_grad():
            outputs = model(**encoded)
            token_embeddings = outputs.last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1).expand(token_embeddings.size()).float()
            summed = torch.sum(token_embeddings * mask, dim=1)
            counts = torch.clamp(mask.sum(dim=1), min=1e-9)
            mean_pooled = summed / counts
        embeddings_list.append(mean_pooled.cpu().numpy().astype(np.float32))
        completed = min(start + BATCH_SIZE, len(texts))
        if completed % 640 == 0 or completed == len(texts):
            print(f"Embedded {completed}/{len(texts)} reports")

    all_embeddings = np.vstack(embeddings_list)
    print(f"Generated embeddings array shape: {all_embeddings.shape}")
    np.save(embeddings_file, all_embeddings)
    with open(metadata_file, "w") as f:
        json.dump({"num_records": len(records), "embedding_dim": int(all_embeddings.shape[1]), "embedding_model": EMBEDDING_MODEL, "max_length": MAX_LENGTH}, f, indent=2)
    print(f"Embeddings saved to cache: {embeddings_file}")
    return all_embeddings

def evaluate_classifier(model, label_encoder, X_test, y_test, title="CLASSIFIER EVALUATION"):
    from sklearn.metrics import accuracy_score, precision_recall_fscore_support, classification_report, confusion_matrix
    y_pred = model.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    macro_p, macro_r, macro_f1, _ = precision_recall_fscore_support(y_test, y_pred, average="macro", zero_division=0)
    weighted_p, weighted_r, weighted_f1, _ = precision_recall_fscore_support(y_test, y_pred, average="weighted", zero_division=0)
    per_class_p, per_class_r, per_class_f1, per_class_supp = precision_recall_fscore_support(y_test, y_pred, average=None, zero_division=0)
    class_names = list(label_encoder.classes_)

    report_str = classification_report(y_test, y_pred, target_names=class_names, zero_division=0)
    cm = confusion_matrix(y_test, y_pred)
    print("\n" + "=" * 60)
    print(f"{title}")
    print("=" * 60)
    print(f"Accuracy   : {acc:.4f}")
    print(f"Macro P    : {macro_p:.4f} | Macro R: {macro_r:.4f} | Macro F1: {macro_f1:.4f} | Weighted F1: {weighted_f1:.4f}")
    print("\nClassification Report:\n" + report_str)
    print("Confusion Matrix:\n", cm)
    print("=" * 60 + "\n")
    per_class_dict = {cname: {"precision": float(per_class_p[idx]), "recall": float(per_class_r[idx]), "f1": float(per_class_f1[idx]), "support": int(per_class_supp[idx])} for idx, cname in enumerate(class_names)}
    return {"accuracy": float(acc), "macro_precision": float(macro_p), "macro_recall": float(macro_r), "macro_f1": float(macro_f1), "weighted_precision": float(weighted_p), "weighted_recall": float(weighted_r), "weighted_f1": float(weighted_f1), "per_class": per_class_dict, "confusion_matrix": cm.tolist()}

def train_lsr_classifier(all_embeddings, records):
    print("\n" + "#" * 60)
    print("TRAINING LSR CLASSIFIER")
    print("#" * 60)
    indices = [idx for idx, r in enumerate(records) if r.get("sif_label") == 1 and r.get("life_saving_rule") not in ["Unclassified", "N/A"]]
    labels = [records[idx].get("life_saving_rule") for idx in indices]
    print(f"Filtered {len(indices)} eligible SIF reports for LSR training.")
    X_lsr = all_embeddings[indices]
    y_lsr_raw = np.array(labels)
    from sklearn.preprocessing import LabelEncoder
    from sklearn.model_selection import train_test_split
    from xgboost import XGBClassifier
    le = LabelEncoder()
    y_lsr = le.fit_transform(y_lsr_raw)
    print(f"LSR Classes ({len(le.classes_)}): {list(le.classes_)}")
    X_train, X_temp, y_train, y_temp = train_test_split(X_lsr, y_lsr, test_size=0.30, random_state=RANDOM_STATE, stratify=y_lsr)
    X_val, X_test, y_val, y_test = train_test_split(X_temp, y_temp, test_size=0.50, random_state=RANDOM_STATE, stratify=y_temp)
    print(f"LSR Train samples: {len(X_train)}, Val samples: {len(X_val)}, Test samples: {len(X_test)}")

    model = XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8, objective="multi:softprob", eval_metric="mlogloss", random_state=RANDOM_STATE, n_jobs=1, tree_method="hist", verbosity=1)
    print("Training XGBoost LSR Classifier...")
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    print("XGBoost LSR Classifier training completed.")
    val_metrics = evaluate_classifier(model, le, X_val, y_val, title="LSR VALIDATION PERFORMANCE")
    test_metrics = evaluate_classifier(model, le, X_test, y_test, title="LSR FINAL TEST PERFORMANCE")
    artifact_path = MODELS_DIR / 'lsr_classifier.joblib'
    artifact = {"model": model, "label_encoder": le, "classes": list(le.classes_), "embedding_model": EMBEDDING_MODEL, "max_length": MAX_LENGTH, "metrics": {"validation": val_metrics, "test": test_metrics}}
    joblib.dump(artifact, artifact_path)
    print(f"LSR Classifier artifact saved to: {artifact_path}\n")
    return test_metrics, list(le.classes_)

def train_activity_classifier(all_embeddings, records):
    print("\n" + "#" * 60)
    print("TRAINING ACTIVITY CLASSIFIER (16 ORIGINAL CLASSES)")
    print("#" * 60)
    X_act = all_embeddings
    y_act_raw = np.array([r.get("activity") for r in records])
    from sklearn.preprocessing import LabelEncoder
    from sklearn.model_selection import train_test_split
    from xgboost import XGBClassifier
    le = LabelEncoder()
    y_act = le.fit_transform(y_act_raw)
    print(f"Activity Classes ({len(le.classes_)}): {list(le.classes_)}")
    X_train, X_temp, y_train, y_temp = train_test_split(X_act, y_act, test_size=0.30, random_state=RANDOM_STATE, stratify=y_act)
    X_val, X_test, y_val, y_test = train_test_split(X_temp, y_temp, test_size=0.50, random_state=RANDOM_STATE, stratify=y_temp)
    print(f"Activity Train samples: {len(X_train)}, Val samples: {len(X_val)}, Test samples: {len(X_test)}")

    model = XGBClassifier(n_estimators=200, max_depth=4, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8, objective="multi:softprob", eval_metric="mlogloss", random_state=RANDOM_STATE, n_jobs=1, tree_method="hist", verbosity=1)
    print("Training XGBoost Activity Classifier...")
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    print("XGBoost Activity Classifier training completed.")
    val_metrics = evaluate_classifier(model, le, X_val, y_val, title="ACTIVITY VALIDATION PERFORMANCE")
    test_metrics = evaluate_classifier(model, le, X_test, y_test, title="ACTIVITY FINAL TEST PERFORMANCE")
    artifact_path = MODELS_DIR / 'activity_classifier.joblib'
    artifact = {"model": model, "label_encoder": le, "classes": list(le.classes_), "embedding_model": EMBEDDING_MODEL, "max_length": MAX_LENGTH, "metrics": {"validation": val_metrics, "test": test_metrics}}
    joblib.dump(artifact, artifact_path)
    print(f"Activity Classifier artifact saved to: {artifact_path}\n")
    return test_metrics, list(le.classes_)

def main():
    parser = argparse.ArgumentParser(description="Train LSR and Activity XGBoost Classifiers")
    parser.add_argument("--embed-only", action="store_true", help="Generate and cache embeddings only")
    parser.add_argument("--train-only", action="store_true", help="Train models from cached embeddings")
    args = parser.parse_args()
    records = load_dataset()
    print_dataset_statistics(records)
    if args.embed_only:
        generate_and_cache_embeddings(records)
        print("Embedding generation completed.")
        return
    embeddings = generate_and_cache_embeddings(records)
    if args.train_only:
        print("Running training phase only...")
    lsr_metrics, lsr_classes = train_lsr_classifier(embeddings, records)
    act_metrics, act_classes = train_activity_classifier(embeddings, records)
    print("\n" + "=" * 60)
    print("ALL PHASE 1 MODEL TRAINING COMPLETED SUCCESSFULLY")
    print("=" * 60)
    print(f"LSR Model Saved      : {MODELS_DIR / 'lsr_classifier.joblib'}")
    print(f"Activity Model Saved : {MODELS_DIR / 'activity_classifier.joblib'}")
    print(f"LSR Test Macro F1    : {lsr_metrics['macro_f1']:.4f}")
    print(f"Activity Test Macro F1: {act_metrics['macro_f1']:.4f}")
    print("Existing sif_classifier.joblib remained UNTOUCHED.")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
