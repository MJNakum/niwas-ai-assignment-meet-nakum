import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.model import (
    load_or_train_model,
    predict_application,
    top_feature_explanation,
    utc_now_iso,
)
from app.schemas import (
    BatchPredictionRequest,
    BatchPredictionResponse,
    ExplanationResponse,
    HealthResponse,
    LoanApplication,
    ModelInfo,
    PredictionResponse,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("credit_risk_api")


def validation_detail(error: Dict[str, Any]) -> str:
    field = str(error.get("loc", ["field"])[-1])
    value = error.get("input")

    if field == "foir":
        return f"foir must be between 0.01 and 0.95, got: {float(value):.2f}"
    if field == "ltv":
        return f"ltv must be between 0.10 and 0.99, got: {float(value):.2f}"
    if field == "bureau_score":
        return f"bureau_score must be between 300 and 900, got: {value}"
    if field == "applicant_id":
        return "applicant_id must be a non-empty string"
    if field == "applications":
        return "applications list length must be between 1 and 50"

    return str(error.get("msg", "Invalid request body"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        artifact = load_or_train_model()
        app.state.model = artifact["model"]
        app.state.model_metadata = artifact["metadata"]
        app.state.model_loaded = True
        logger.info("[STARTUP] model_loaded=true model_version=%s", artifact["metadata"]["model_version"])
    except Exception as exc:
        app.state.model = None
        app.state.model_metadata = {}
        app.state.model_loaded = False
        logger.exception("[STARTUP] model_loaded=false error=%s", exc)
    yield


app = FastAPI(title="Niwas Credit Risk API", version="1.0.0", lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    first_error = exc.errors()[0] if exc.errors() else {"msg": "Invalid request body"}
    return JSONResponse(
        status_code=422,
        content={"error": "VALIDATION_ERROR", "detail": validation_detail(first_error)},
    )


def prediction_error_response() -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "PREDICTION_ERROR",
            "message": "Model inference failed",
            "timestamp": utc_now_iso(),
        },
    )


def model_or_raise(request: Request):
    if not getattr(request.app.state, "model_loaded", False) or request.app.state.model is None:
        raise RuntimeError("Model is not loaded")
    return request.app.state.model


def prediction_payload(request: Request, application: LoanApplication) -> PredictionResponse:
    start_time = time.perf_counter()
    model = model_or_raise(request)
    risk_label, risk_probability = predict_application(model, application)
    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

    logger.info(
        "[PREDICTION] applicant_id=%s foir=%.2f ltv=%.2f bureau_score=%s "
        "risk_label=%s risk_probability=%.2f latency_ms=%.2f",
        application.applicant_id,
        application.foir,
        application.ltv,
        application.bureau_score,
        risk_label,
        risk_probability,
        latency_ms,
    )

    return PredictionResponse(
        applicant_id=application.applicant_id,
        risk_label=risk_label,
        risk_probability=risk_probability,
        model_version=request.app.state.model_metadata["model_version"],
        timestamp=utc_now_iso(),
    )


@app.post("/predict", response_model=PredictionResponse)
async def predict(application: LoanApplication, request: Request):
    try:
        return prediction_payload(request, application)
    except Exception:
        logger.exception("[ERROR] prediction_failed applicant_id=%s", application.applicant_id)
        return prediction_error_response()


@app.post("/predict/batch", response_model=BatchPredictionResponse)
async def predict_batch(payload: BatchPredictionRequest, request: Request):
    try:
        predictions = [prediction_payload(request, application) for application in payload.applications]
        return BatchPredictionResponse(
            predictions=predictions,
            summary={
                "total": len(predictions),
                "high_risk_count": sum(item.risk_label == "HIGH" for item in predictions),
                "medium_risk_count": sum(item.risk_label == "MEDIUM" for item in predictions),
                "low_risk_count": sum(item.risk_label == "LOW" for item in predictions),
            },
        )
    except Exception:
        logger.exception("[ERROR] batch_prediction_failed")
        return prediction_error_response()


@app.get("/model/info", response_model=ModelInfo)
async def model_info(request: Request):
    if not getattr(request.app.state, "model_loaded", False):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": "MODEL_NOT_LOADED", "message": "Model is not loaded"},
        )
    return request.app.state.model_metadata


@app.get("/health", response_model=HealthResponse)
async def health(request: Request):
    if getattr(request.app.state, "model_loaded", False):
        return {"status": "healthy"}
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "model_not_loaded"},
    )


@app.post("/explain", response_model=ExplanationResponse)
async def explain(application: LoanApplication, request: Request):
    try:
        model = model_or_raise(request)
        return top_feature_explanation(model, application)
    except Exception:
        logger.exception("[ERROR] explanation_failed applicant_id=%s", application.applicant_id)
        return prediction_error_response()
