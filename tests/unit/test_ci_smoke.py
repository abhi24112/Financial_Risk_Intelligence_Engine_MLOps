"""
tests/unit/test_ci_smoke.py

Fast, lightweight CI Smoke Test Suite.
Designed for GitHub Actions CI to fail fast (<5s execution) without requiring
live external dependencies (PostgreSQL, Redis).
"""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from api.schemas import (
    BatchTransactionRequest,
    TransactionRequest,
)


def test_configs_exist_and_valid():
    """Ensure core configuration files exist and parse as valid YAML."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    configs_dir = repo_root / "configs"

    assert configs_dir.exists(), "configs/ directory must exist"

    # Verify api.yaml
    api_yaml = configs_dir / "api.yaml"
    assert api_yaml.exists(), "configs/api.yaml must exist"
    with open(api_yaml, encoding="utf-8") as f:
        api_cfg = yaml.safe_load(f)
    assert "app" in api_cfg, "api.yaml missing 'app' section"
    assert "server" in api_cfg, "api.yaml missing 'server' section"

    # Verify model.yaml
    model_yaml = configs_dir / "model.yaml"
    assert model_yaml.exists(), "configs/model.yaml must exist"
    with open(model_yaml, encoding="utf-8") as f:
        model_cfg = yaml.safe_load(f)
    assert isinstance(model_cfg, dict), "model.yaml should parse as a dictionary"


def test_transaction_schema_valid():
    """Verify TransactionRequest schema accepts valid transaction payloads."""
    payload = {
        "TransactionAmt": 105.50,
        "TransactionDT": 86400,
        "card1": "1000",
        "card2": "111",
        "ProductCD": "W",
        "addr2": "87.0",
        "P_emaildomain": "gmail.com",
        "DeviceType": "desktop",
    }
    tx = TransactionRequest(**payload)
    assert tx.TransactionAmt == 105.50
    assert tx.TransactionDT == 86400
    assert tx.card1 == "1000"
    assert tx.ProductCD == "W"


def test_transaction_schema_invalid_amount():
    """Verify TransactionRequest schema rejects negative or zero amounts."""
    with pytest.raises(ValidationError):
        TransactionRequest(TransactionAmt=-50.0, TransactionDT=86400)

    with pytest.raises(ValidationError):
        TransactionRequest(TransactionAmt=0.0, TransactionDT=86400)


def test_batch_transaction_schema():
    """Verify BatchTransactionRequest handles multiple items and rejects empty list."""
    valid_batch = {
        "transactions": [
            TransactionRequest(TransactionAmt=10.0, TransactionDT=100),
            TransactionRequest(TransactionAmt=25.5, TransactionDT=200),
        ]
    }
    batch = BatchTransactionRequest(**valid_batch)
    assert len(batch.transactions) == 2

    with pytest.raises(ValidationError):
        BatchTransactionRequest(transactions=[])


def test_fastapi_app_health_smoke():
    """Verify FastAPI application boots and responds to /health probe."""
    from fastapi.testclient import TestClient

    from api.app import create_app

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "model_loaded" in data
        assert "version" in data
