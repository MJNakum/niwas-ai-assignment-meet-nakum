from fastapi.testclient import TestClient

from app.main import app
from app.model import label_from_probability


def test_valid_single_prediction_returns_expected_fields():
    with TestClient(app) as client:
        response = client.post(
            "/predict",
            json={
                "applicant_id": "APP-2026-001",
                "foir": 0.45,
                "ltv": 0.72,
                "bureau_score": 690,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["applicant_id"] == "APP-2026-001"
    assert body["risk_label"] in {"LOW", "MEDIUM", "HIGH"}
    assert 0 <= body["risk_probability"] <= 1
    assert body["model_version"] == "v1.0"
    assert "timestamp" in body


def test_batch_prediction_returns_summary_counts():
    with TestClient(app) as client:
        response = client.post(
            "/predict/batch",
            json={
                "applications": [
                    {"applicant_id": "APP-001", "foir": 0.30, "ltv": 0.60, "bureau_score": 750},
                    {"applicant_id": "APP-002", "foir": 0.75, "ltv": 0.90, "bureau_score": 560},
                ]
            },
        )

    assert response.status_code == 200
    body = response.json()
    summary = body["summary"]
    assert len(body["predictions"]) == 2
    assert summary["total"] == 2
    assert (
        summary["high_risk_count"]
        + summary["medium_risk_count"]
        + summary["low_risk_count"]
        == 2
    )


def test_invalid_foir_returns_structured_validation_error():
    with TestClient(app) as client:
        response = client.post(
            "/predict",
            json={
                "applicant_id": "APP-2026-001",
                "foir": 1.20,
                "ltv": 0.72,
                "bureau_score": 690,
            },
        )

    assert response.status_code == 422
    assert response.json() == {
        "error": "VALIDATION_ERROR",
        "detail": "foir must be between 0.01 and 0.95, got: 1.20",
    }


def test_health_returns_healthy_when_model_loaded():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_risk_label_boundary_mapping():
    assert label_from_probability(0.60) == "HIGH"
    assert label_from_probability(0.59) == "MEDIUM"
    assert label_from_probability(0.35) == "MEDIUM"
    assert label_from_probability(0.34) == "LOW"


def test_explain_returns_top_feature_and_explanation():
    with TestClient(app) as client:
        response = client.post(
            "/explain",
            json={
                "applicant_id": "APP-001",
                "foir": 0.62,
                "ltv": 0.85,
                "bureau_score": 610,
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["applicant_id"] == "APP-001"
    assert body["top_feature"] in {"foir", "ltv", "bureau_score"}
    assert 0 <= body["feature_importance"] <= 1
    assert "strongest risk driver" in body["explanation"]
