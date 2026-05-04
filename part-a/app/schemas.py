from typing import List
from typing import Optional

from pydantic import BaseModel, Field


class LoanApplication(BaseModel):
    applicant_id: str = Field(..., min_length=1)
    foir: float = Field(..., ge=0.01, le=0.95)
    ltv: float = Field(..., ge=0.10, le=0.99)
    bureau_score: int = Field(..., ge=300, le=900)


class BatchPredictionRequest(BaseModel):
    applications: List[LoanApplication] = Field(..., min_length=1, max_length=50)


class PredictionResponse(BaseModel):
    applicant_id: str
    risk_label: str
    risk_probability: float
    model_version: str
    timestamp: str


class BatchSummary(BaseModel):
    total: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int


class BatchPredictionResponse(BaseModel):
    predictions: List[PredictionResponse]
    summary: BatchSummary


class ModelInfo(BaseModel):
    model_name: str
    model_version: str
    algorithm: str
    features: List[str]
    training_data_size: int
    trained_at: str
    sklearn_version: Optional[str] = None


class HealthResponse(BaseModel):
    status: str


class ExplanationResponse(BaseModel):
    applicant_id: str
    top_feature: str
    feature_importance: float
    explanation: str
