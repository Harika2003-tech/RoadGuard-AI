"""Reproduce the RoadGuard AI paper metrics from the shipped model and dataset.
Run from the project root after installing requirements.txt.
"""
import json
from pathlib import Path
import joblib
import pandas as pd
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix, precision_recall_fscore_support,
)
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "datasets" / "roadguard_realworld_derived.csv"
MODEL = ROOT / "roadguard_model.joblib"
OUT = ROOT / "research" / "reproduced_metrics.json"

bundle = joblib.load(MODEL)
data = pd.read_csv(DATA)
features = bundle["features"]
X, y = data[features], data["risk_label"].astype(int)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
pred = bundle["model"].predict(bundle["scaler"].transform(X_test))
cm = confusion_matrix(y_test, pred, labels=[0, 1, 2])
p, r, f, support = precision_recall_fscore_support(y_test, pred, labels=[0, 1, 2], zero_division=0)
classes = ["Low", "Moderate", "High"]
report = {
    "dataset": "datasets/roadguard_realworld_derived.csv",
    "records": int(len(data)),
    "train_records": int(len(X_train)),
    "test_records": int(len(X_test)),
    "split": "stratified 80:20; random_state=42",
    "model": "RandomForestClassifier(n_estimators=180, max_depth=10, random_state=42, class_weight='balanced')",
    "accuracy_percent": round(accuracy_score(y_test, pred)*100, 2),
    "weighted_precision_percent": round(precision_score(y_test, pred, average="weighted", zero_division=0)*100, 2),
    "weighted_recall_percent": round(recall_score(y_test, pred, average="weighted", zero_division=0)*100, 2),
    "weighted_f1_percent": round(f1_score(y_test, pred, average="weighted", zero_division=0)*100, 2),
    "confusion_matrix_actual_rows_predicted_columns_low_moderate_high": cm.tolist(),
    "class_metrics_percent": {
        name: {"precision": round(float(p[i])*100, 2), "recall": round(float(r[i])*100, 2),
              "f1": round(float(f[i])*100, 2), "support": int(support[i])}
        for i, name in enumerate(classes)
    },
}
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
