import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app

# Add project root to sys.path if not present
root_dir = str(Path(__file__).resolve().parent.parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)


@pytest.fixture(scope="module")
def client():
    """Test client fixture initialized with app lifespan."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "model_loaded" in data
    assert "redis_connected" in data
    assert "version" in data


def test_ready_check(client: TestClient):
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


def test_ui_dashboard(client: TestClient):
    response = client.get("/ui")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Adaptive Financial Risk Intelligence Engine" in response.text


def test_predict_single_normal_transaction(client: TestClient):
    payload = {
        "TransactionAmt": 15.50,
        "TransactionDT": 86400,
        "card1": "1000",
        "card2": "111",
        "ProductCD": "W",
        "addr2": "87.0",
        "P_emaildomain": "gmail.com",
        "DeviceType": "desktop",
    }
    response = client.post("/predict", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert 0 <= data["risk_score"] <= 100
    assert data["risk_level"] in ["Low", "Medium", "High"]
    assert 0.0 <= data["fraud_probability"] <= 1.0
    assert data["latency_ms"] >= 0

    # Verify custom middleware headers
    assert "X-Request-ID" in response.headers
    assert "X-Response-Time-Ms" in response.headers


def test_predict_single_suspicious_transaction(client: TestClient):
    payload = {
        "TransactionAmt": 9500.00,
        "TransactionDT": 3600,
        "card1": "9999",
        "card2": "999",
        "ProductCD": "C",
        "addr2": None,
        "P_emaildomain": "anonymous.com",
        "DeviceType": "mobile",
    }
    response = client.post("/predict", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert 0 <= data["risk_score"] <= 100
    assert data["risk_level"] in ["Low", "Medium", "High"]


def test_predict_validation_error(client: TestClient):
    # Invalid negative amount should fail Pydantic validation (gt=0)
    payload = {
        "TransactionAmt": -50.0,
        "TransactionDT": 86400,
    }
    response = client.post("/predict", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert "error" in data or "details" in data


def test_predict_batch_transactions(client: TestClient):
    payload = {
        "transactions": [
            {"TransactionAmt": 20.0, "TransactionDT": 86400, "card1": "1000", "card2": "111"},
            {"TransactionAmt": 8500.0, "TransactionDT": 3600, "card1": "9999", "card2": "999"},
            {"TransactionAmt": 120.5, "TransactionDT": 90000, "card1": "2000", "card2": "222"},
        ]
    }
    response = client.post("/predict/batch", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["total_transactions"] == 3
    assert len(data["predictions"]) == 3
    assert data["batch_latency_ms"] >= 0
    assert data["throughput_tx_per_sec"] >= 0

    for pred in data["predictions"]:
        assert 0 <= pred["risk_score"] <= 100
        assert pred["risk_level"] in ["Low", "Medium", "High"]


def test_explain_endpoint(client: TestClient):
    payload = {
        "transaction": {
            "TransactionAmt": 750.00,
            "TransactionDT": 86400,
            "card1": "1000",
            "card2": "111",
            "ProductCD": "W",
            "addr2": "87.0",
            "P_emaildomain": "gmail.com",
            "DeviceType": "desktop",
        },
        "top_k": 3,
    }
    response = client.post("/explain", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert 0 <= data["risk_score"] <= 100
    assert "reasons" in data
    assert isinstance(data["reasons"], list)
    assert len(data["reasons"]) <= 3
    assert "top_features" in data
    assert "shap_values" in data
