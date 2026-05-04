import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier

from app.data import TRAINING_DATA
from app.schemas import LoanApplication

MODEL_NAME = "credit_risk_classifier"
MODEL_VERSION = "v1.0"
ALGORITHM = "RandomForestClassifier"
FEATURES = ["foir", "ltv", "bureau_score"]
MODEL_PATH = Path("models") / "credit_risk_model.pkl"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def train_model() -> Dict[str, Any]:
    frame = pd.DataFrame(TRAINING_DATA)
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=4,
        random_state=42,
        class_weight="balanced",
    )
    model.fit(frame[FEATURES], frame["label"])

    artifact = {
        "model": model,
        "metadata": {
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "algorithm": ALGORITHM,
            "features": FEATURES,
            "training_data_size": len(TRAINING_DATA),
            "trained_at": utc_now_iso(),
            "sklearn_version": sklearn.__version__,
        },
    }

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MODEL_PATH.open("wb") as file:
        pickle.dump(artifact, file)

    return artifact


def load_or_train_model() -> Dict[str, Any]:
    if not MODEL_PATH.exists():
        return train_model()

    try:
        with MODEL_PATH.open("rb") as file:
            artifact = pickle.load(file)
        # Force a tiny inference so incompatible sklearn tree pickles fail at startup.
        artifact["model"].predict_proba(pd.DataFrame([[0.45, 0.72, 690]], columns=FEATURES))
        return artifact
    except Exception:
        return train_model()


def label_from_probability(probability: float) -> str:
    if probability >= 0.60:
        return "HIGH"
    if probability >= 0.35:
        return "MEDIUM"
    return "LOW"


def features_for_application(application: LoanApplication) -> pd.DataFrame:
    return pd.DataFrame(
        [[application.foir, application.ltv, application.bureau_score]],
        columns=FEATURES,
    )


def predict_application(model: Any, application: LoanApplication) -> Tuple[str, float]:
    probability = float(model.predict_proba(features_for_application(application))[0][1])
    probability = round(probability, 2)
    return label_from_probability(probability), probability


def top_feature_explanation(model: Any, application: LoanApplication) -> Dict[str, Any]:
    importances = list(model.feature_importances_)
    top_index = max(range(len(importances)), key=lambda index: importances[index])
    top_feature = FEATURES[top_index]
    feature_value = getattr(application, top_feature)

    return {
        "applicant_id": application.applicant_id,
        "top_feature": top_feature,
        "feature_importance": round(float(importances[top_index]), 2),
        "explanation": f"{top_feature} value of {feature_value} is the strongest risk driver",
    }
