from datetime import datetime

from pydantic import BaseModel, Field


class TransactionRequest(BaseModel):
    """
    Schema for a single financial transaction request.
    Permits dynamic IEEE-CIS features via extra='allow'.
    """

    TransactionAmt: float = Field(..., gt=0, description="Transaction amount in USD", examples=[150.50])
    TransactionDT: int = Field(..., ge=0, description="Timedelta in seconds from reference point", examples=[86400])
    card1: str | None = Field(default=None, description="Primary card ID / BIN", examples=["1000"])
    card2: str | None = Field(default=None, description="Secondary card attribute", examples=["111"])
    ProductCD: str | None = Field(default=None, description="Product code (e.g. W, C, H, R)", examples=["W"])
    addr2: str | None = Field(default=None, description="Country/Address code", examples=["87.0"])
    P_emaildomain: str | None = Field(default=None, description="Purchaser email domain", examples=["gmail.com"])
    DeviceType: str | None = Field(default=None, description="Device type (e.g. desktop, mobile)", examples=["desktop"])
    DeviceInfo: str | None = Field(default=None, description="Device brand / OS info", examples=["iOS Device"])

    model_config = {
        "extra": "allow",
        "json_schema_extra": {
            "example": {
                "TransactionAmt": 150.50,
                "TransactionDT": 86400,
                "card1": "1000",
                "card2": "111",
                "ProductCD": "W",
                "addr2": "87.0",
                "P_emaildomain": "gmail.com",
                "DeviceType": "desktop",
            }
        },
    }


class PredictionResponse(BaseModel):
    """
    Schema for transaction risk scoring response.
    """

    transaction_id: str | None = Field(default=None, description="Transaction identifier")
    risk_score: int = Field(..., ge=0, le=100, description="Risk score from 0 (Safe) to 100 (High Risk)")
    risk_level: str = Field(..., description="Categorical risk level: Low, Medium, High")
    fraud_probability: float = Field(..., ge=0.0, le=1.0, description="Model raw probability of fraud")
    latency_ms: float = Field(..., description="Inference latency in milliseconds")
    request_id: str | None = Field(default=None, description="Unique correlation ID for tracing")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z", description="ISO 8601 UTC timestamp")


class BatchTransactionRequest(BaseModel):
    """
    Schema for high-throughput batch transaction scoring.
    """

    transactions: list[TransactionRequest] = Field(..., min_length=1, max_length=500, description="List of transactions to score (max 500 per batch)")


class BatchPredictionResponse(BaseModel):
    """
    Schema for batch prediction response with throughput telemetry.
    """

    predictions: list[PredictionResponse] = Field(..., description="List of risk evaluations")
    total_transactions: int = Field(..., description="Number of scored transactions")
    batch_latency_ms: float = Field(..., description="Total batch processing latency in milliseconds")
    throughput_tx_per_sec: float = Field(..., description="Calculated throughput (transactions / second)")


class ExplainRequest(BaseModel):
    """
    Schema for requesting SHAP explainability on a transaction.
    """

    transaction: TransactionRequest = Field(..., description="Transaction payload to explain")
    top_k: int = Field(default=3, ge=1, le=10, description="Number of top influential features to return")


class ExplainResponse(BaseModel):
    """
    Schema for analyst-readable SHAP explanations.
    """

    transaction_id: str | None = Field(default=None, description="Transaction identifier")
    risk_score: int = Field(..., ge=0, le=100, description="Risk score from 0 to 100")
    risk_level: str = Field(..., description="Risk tier: Low, Medium, or High")
    fraud_probability: float = Field(..., description="Calibrated fraud probability")
    top_features: list[str] = Field(..., description="Top contributing feature names")
    shap_values: list[float] = Field(..., description="Raw SHAP attribution values")
    reasons: list[str] = Field(..., description="Human-readable explanations for risk analysts")
    latency_ms: float = Field(..., description="Explanation computation time in ms")


class HealthResponse(BaseModel):
    """
    Schema for liveness and readiness probe.
    """

    status: str = Field(..., description="Overall service status (e.g. 'healthy', 'degraded')")
    model_loaded: bool = Field(..., description="Whether the ML Champion model is active in memory")
    redis_connected: bool = Field(..., description="Whether Redis Feature Store is reachable")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    version: str = Field(default="1.0.0", description="API version")
