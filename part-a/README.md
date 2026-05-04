# Niwas Credit Risk API - Part A

FastAPI service for scoring home loan applications with a binary credit risk model.

## Model Choice

I chose `RandomForestClassifier` over logistic regression for this assignment. The dataset is small and tabular, and random forest can capture non-linear relationships between FOIR, LTV, and bureau score without requiring feature scaling. It also exposes `feature_importances_`, which supports the optional `/explain` endpoint cleanly.

The trained model is saved to `models/credit_risk_model.pkl`. At API startup, the app trains and saves the model if the file is missing, then loads the `.pkl` artifact before serving requests.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Run the API:

```bash
uvicorn app.main:app --reload
```

Run tests:

```bash
pytest
```

## Endpoints

### Health Check

```bash
curl http://127.0.0.1:8000/health
```

Response:

```json
{
  "status": "healthy"
}
```

### Model Info

```bash
curl http://127.0.0.1:8000/model/info
```

Response:

```json
{
  "model_name": "credit_risk_classifier",
  "model_version": "v1.0",
  "algorithm": "RandomForestClassifier",
  "features": ["foir", "ltv", "bureau_score"],
  "training_data_size": 28,
  "trained_at": "2026-05-04T17:30:00Z",
  "sklearn_version": "1.8.0"
}
```

### Single Prediction

```bash
curl -X POST http://127.0.0.1:8000/predict ^
  -H "Content-Type: application/json" ^
  -d "{\"applicant_id\":\"APP-2026-001\",\"foir\":0.45,\"ltv\":0.72,\"bureau_score\":690}"
```

Response:

```json
{
  "applicant_id": "APP-2026-001",
  "risk_label": "LOW",
  "risk_probability": 0.18,
  "model_version": "v1.0",
  "timestamp": "2026-05-04T17:30:00Z"
}
```

Risk label thresholds:

- `HIGH`: probability >= `0.60`
- `MEDIUM`: probability from `0.35` to `0.59`
- `LOW`: probability < `0.35`

### Batch Prediction

```bash
curl -X POST http://127.0.0.1:8000/predict/batch ^
  -H "Content-Type: application/json" ^
  -d "{\"applications\":[{\"applicant_id\":\"APP-001\",\"foir\":0.45,\"ltv\":0.72,\"bureau_score\":690},{\"applicant_id\":\"APP-002\",\"foir\":0.62,\"ltv\":0.85,\"bureau_score\":610}]}"
```

Response:

```json
{
  "predictions": [
    {
      "applicant_id": "APP-001",
      "risk_label": "LOW",
      "risk_probability": 0.18,
      "model_version": "v1.0",
      "timestamp": "2026-05-04T17:30:00Z"
    }
  ],
  "summary": {
    "total": 2,
    "high_risk_count": 1,
    "medium_risk_count": 0,
    "low_risk_count": 1
  }
}
```

The batch endpoint accepts 1 to 50 applications.

### Explain Prediction

```bash
curl -X POST http://127.0.0.1:8000/explain ^
  -H "Content-Type: application/json" ^
  -d "{\"applicant_id\":\"APP-001\",\"foir\":0.62,\"ltv\":0.85,\"bureau_score\":610}"
```

Response:

```json
{
  "applicant_id": "APP-001",
  "top_feature": "foir",
  "feature_importance": 0.51,
  "explanation": "foir value of 0.62 is the strongest risk driver"
}
```

## Validation and Errors

Request validation uses Pydantic constraints:

- `foir`: `0.01` to `0.95`
- `ltv`: `0.10` to `0.99`
- `bureau_score`: `300` to `900`
- `applicant_id`: non-empty string
- batch size: `1` to `50`

Example validation error:

```json
{
  "error": "VALIDATION_ERROR",
  "detail": "foir must be between 0.01 and 0.95, got: 1.20"
}
```

Unexpected prediction errors return HTTP 500:

```json
{
  "error": "PREDICTION_ERROR",
  "message": "Model inference failed",
  "timestamp": "2026-05-04T17:30:00Z"
}
```

Each prediction logs a structured line:

```text
[PREDICTION] applicant_id=APP-001 foir=0.45 ltv=0.72 bureau_score=690 risk_label=LOW risk_probability=0.18 latency_ms=3.20
```
