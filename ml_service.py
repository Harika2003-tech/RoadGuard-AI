"""RoadGuard AI data processing, model training, evaluation and prediction."""
from pathlib import Path
import hashlib
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, confusion_matrix, f1_score, precision_score,
    recall_score, precision_recall_fscore_support,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent
MODEL = ROOT / "roadguard_model.joblib"
FEATURES = ["speed", "acceleration", "braking", "duration", "weather", "traffic", "road_condition"]
CLASS_NAMES = {0: "Low", 1: "Moderate", 2: "High"}


def demo_dataset(rows=1800):
    """Synthetic demonstration data only; not the paper's real-world experiment."""
    rng = np.random.default_rng(42)
    x = pd.DataFrame({
        "speed": rng.normal(58, 20, rows).clip(5, 150),
        "acceleration": rng.gamma(2, 1.6, rows).clip(0, 15),
        "braking": rng.gamma(2, 1.3, rows).clip(0, 12),
        "duration": rng.uniform(2, 240, rows),
        "weather": rng.integers(0, 4, rows),
        "traffic": rng.integers(0, 4, rows),
        "road_condition": rng.integers(0, 4, rows),
    })
    score = (.38*x.speed + 3*x.acceleration + 4*x.braking + .07*x.duration
             + 5*x.weather + 4*x.traffic + 4*x.road_condition + rng.normal(0, 8, rows))
    x["risk_label"] = np.select([score < 35, score < 65], [0, 1], default=2)
    return x


def _prepare(frame):
    if frame is None:
        data = demo_dataset()
    else:
        data = frame.copy()
    required = FEATURES + ["risk_label"]
    missing = [name for name in required if name not in data.columns]
    if missing:
        raise ValueError(
            "This is not the RoadGuard processed training CSV. Missing columns: "
            + ", ".join(missing)
            + ". For the paper experiment, upload datasets/roadguard_realworld_derived.csv. "
              "The original mmc2.csv is raw source data and must not be uploaded directly."
        )
    before = len(data)
    data = data[required].apply(pd.to_numeric, errors="coerce").dropna().copy()
    if data.empty:
        raise ValueError("No complete numeric training rows remain after missing-value removal.")
    labels = set(data["risk_label"].astype(int).unique())
    if not labels.issubset({0, 1, 2}) or labels != {0, 1, 2}:
        raise ValueError("risk_label must contain all three classes: 0 (Low), 1 (Moderate), 2 (High).")
    if not np.allclose(data["risk_label"], data["risk_label"].astype(int)):
        raise ValueError("risk_label must contain integer class values 0, 1, or 2.")
    data["risk_label"] = data["risk_label"].astype(int)
    return data, before - len(data)


def train(frame=None, source_name="uploaded CSV"):
    data, dropped_rows = _prepare(frame)
    X, y = data[FEATURES], data["risk_label"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    model = RandomForestClassifier(
        n_estimators=180, max_depth=10, random_state=42, class_weight="balanced"
    ).fit(X_train_scaled, y_train)
    predictions = model.predict(X_test_scaled)

    accuracy = accuracy_score(y_test, predictions)
    precision = precision_score(y_test, predictions, average="weighted", zero_division=0)
    recall = recall_score(y_test, predictions, average="weighted", zero_division=0)
    f1 = f1_score(y_test, predictions, average="weighted", zero_division=0)
    matrix = confusion_matrix(y_test, predictions, labels=[0, 1, 2])
    class_p, class_r, class_f, class_support = precision_recall_fscore_support(
        y_test, predictions, labels=[0, 1, 2], zero_division=0
    )
    class_metrics = {
        CLASS_NAMES[i]: {
            "precision": round(float(class_p[i]) * 100, 2),
            "recall": round(float(class_r[i]) * 100, 2),
            "f1Score": round(float(class_f[i]) * 100, 2),
            "support": int(class_support[i]),
        }
        for i in range(3)
    }
    importances = dict(zip(FEATURES, map(float, model.feature_importances_)))
    evaluation = {
        "rows": int(len(data)),
        "trainRows": int(len(X_train)),
        "testRows": int(len(X_test)),
        "droppedRows": int(dropped_rows),
        "accuracy": round(float(accuracy) * 100, 2),
        "precision": round(float(precision) * 100, 2),
        "recall": round(float(recall) * 100, 2),
        "f1Score": round(float(f1) * 100, 2),
        "confusionMatrix": matrix.tolist(),
        "classMetrics": class_metrics,
        "featureImportance": dict(sorted(importances.items(), key=lambda item: -item[1])),
        "split": "stratified 80:20; random_state=42",
        "source": source_name,
    }
    fingerprint = hashlib.sha256(
        pd.util.hash_pandas_object(data, index=False).values.tobytes()
    ).hexdigest()
    bundle = {
        "model": model,
        "scaler": scaler,
        "features": FEATURES,
        "accuracy": float(accuracy),
        "importances": importances,
        "evaluation": evaluation,
        "dataset_sha256_rows": fingerprint,
    }
    joblib.dump(bundle, MODEL)
    return evaluation


def predict(values):
    if not MODEL.exists():
        # This fallback is only for a fresh demo installation. The paper-ready
        # package includes the trained real-world model and does not need it.
        train()
    bundle = joblib.load(MODEL)
    row = pd.DataFrame([[float(values.get(feature, 0)) for feature in FEATURES]], columns=FEATURES)
    probability = bundle["model"].predict_proba(bundle["scaler"].transform(row))[0]
    label = int(bundle["model"].classes_[int(np.argmax(probability))])
    risk = round(float(np.dot(probability, bundle["model"].classes_)) / 2 * 100)
    importance = bundle["importances"]
    contributions = {
        feature: round(float(importance[feature]) * float(row.iloc[0][feature])
                       / max(float(row.iloc[0][feature]), 1), 1)
        for feature in FEATURES
    }
    return {
        "riskScore": risk,
        "riskLevel": CLASS_NAMES[label],
        "confidence": round(float(max(probability)) * 100, 1),
        "featureImportance": importance,
        "explanation": sorted(contributions, key=contributions.get, reverse=True)[:3],
    }
