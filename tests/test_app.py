"""
Tests for the FastAPI microservice (app.py) that exposes /transaction.
Requires: httpx (for TestClient), fastapi, pydantic.
"""

from fastapi.testclient import TestClient

# Import the FastAPI instance from app.py
# If your app file lives elsewhere (e.g., src/app.py), change the import to:
#   from src.app import app as fastapi_app
from app import app as fastapi_app

client = TestClient(fastapi_app)


def test_health():
    """Basic healthcheck should return status ok."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_config_contains_score_mapping():
    """Config endpoint should expose current rule thresholds/weights."""
    r = client.get("/config")
    assert r.status_code == 200
    payload = r.json()
    assert isinstance(payload, dict)
    assert "score_to_decision" in payload
    assert "amount_thresholds" in payload


def test_transaction_in_review_path():
    """Typical medium-risk digital transaction from NEW user at night -> IN_REVIEW."""
    body = {
        "transaction_id": 42,
        "amount_mxn": 5200.0,
        "customer_txn_30d": 1,
        "geo_state": "Nuevo León",
        "device_type": "mobile",
        "chargeback_count": 0,
        "hour": 23,
        "product_type": "digital",
        "latency_ms": 180,
        "user_reputation": "new",
        "device_fingerprint_risk": "low",
        "ip_risk": "medium",
        "email_risk": "new_domain",
        "bin_country": "MX",
        "ip_country": "MX"
    }
    r = client.post("/transaction", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["transaction_id"] == 42
    assert data["decision"] in ("ACCEPTED", "IN_REVIEW", "REJECTED")
    # With the current defaults (reject_at=10, review_at=4), this should lean to IN_REVIEW
    # If you tuned env vars REJECT_AT/REVIEW_AT, this assertion may need adjustment.
    assert data["decision"] == "IN_REVIEW"


def test_transaction_hard_block_rejection():
    """Chargebacks>=2 with ip_risk=high should trigger hard block -> REJECTED."""
    body = {
        "transaction_id": 99,
        "amount_mxn": 300.0,
        "customer_txn_30d": 0,
        "geo_state": "Nuevo León",
        "device_type": "mobile",
        "chargeback_count": 2,
        "hour": 12,
        "product_type": "digital",
        "latency_ms": 100,
        "user_reputation": "new",
        "device_fingerprint_risk": "low",
        "ip_risk": "high",
        "email_risk": "low",
        "bin_country": "MX",
        "ip_country": "MX"
    }
    r = client.post("/transaction", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["transaction_id"] == 99
    assert data["decision"] == "REJECTED"

def test_transaction_frequency_buffer():
    """A recurrent user with a minor risk should have their score reduced by the buffer."""
    body = {
        "transaction_id": 105,
        "user_reputation": "recurrent", 
        "customer_txn_30d": 5,          
        "ip_risk": "high",              
    }
    r = client.post("/transaction", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["transaction_id"] == 105
    assert "frequency_buffer(-1)" in data["reasons"]
    assert data["risk_score"] == 2
    assert data["decision"] == "ACCEPTED"

def test_transaction_geo_mismatch():
    """Transaction with different bin and IP countries should be flagged."""
    body = {
        "transaction_id": 104,
        "bin_country": "US",
        "ip_country": "MX",
        "amount_mxn": 100.0,
        "user_reputation": "new",
        "ip_risk": "low",
    }
    r = client.post("/transaction", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["transaction_id"] == 104
    assert "geo_mismatch:US!=MX(+2)" in data["reasons"]

def test_transaction_latency_extreme():
    """A transaction with very high latency should get a score penalty of 2."""
    body = {
        "transaction_id": 103,
        "latency_ms": 3000,
        "amount_mxn": 100.0,
        "user_reputation": "new",
        "ip_risk": "low",
        "email_risk": "low"
    }
    r = client.post("/transaction", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["transaction_id"] == 103
    assert "latency_extreme:3000ms(+2)" in data["reasons"]
    assert data["decision"] == "ACCEPTED" 

def test_transaction_is_night():
    """A transaction at a night hour should be flagged by the is_night logic."""
    body = {
        "transaction_id": 106,
        "hour": 23,  
        "amount_mxn": 100.0,
        "user_reputation": "new",
        "ip_risk": "low",
        "email_risk": "low",
        "bin_country": "MX",
        "ip_country": "MX"
    }
    r = client.post("/transaction", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["transaction_id"] == 106
    assert "night_hour:23(+1)" in data["reasons"]
    assert data["risk_score"] == 1
    assert data["decision"] == "ACCEPTED"

#def test_transaction_high_amount():
    #"""A transaction with a high amount for its product type should be flagged by the high_amount logic. High amount and new user -> IN_REVIEW"""
    #body = {
    #    "transaction_id": 107,
    #    "product_type": "digital",
    #    "amount_mxn": 3000,  
    #    "user_reputation": "new", 
    #    "hour": 15,
    #    "ip_risk": "low",
    #    "email_risk": "low",
    #    "bin_country": "MX",
    #    "ip_country": "MX"
    #}
    #r = client.post("/transaction", json=body)
    #assert r.status_code == 200, r.text
    #data = r.json()
    #assert data["transaction_id"] == 107
    #assert "high_amount:digital:3000(+2)" in data["reasons"]
    #assert "new_user_high_amount(+2)" in data["reasons"]
    #assert data["risk_score"] == 4
    #assert data["decision"] == "IN_REVIEW"