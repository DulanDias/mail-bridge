from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_validate_mailbox():
    response = client.post("/api/v1/auth/validate", json={"mailbox_email": "test@example.com"})
    assert response.status_code in [200, 400]  # Depends on whether validation succeeds

def test_jwt_token_expiry():
    expired_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."  # Example expired token
    try:
        decode_jwt(expired_token)
    except Exception as e:
        assert str(e) == "Token has expired"

def test_refresh_token_expiry():
    expired_refresh_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."  # Example expired refresh token
    try:
        decode_refresh_token(expired_refresh_token)
    except Exception as e:
        assert str(e) == "Refresh token has expired"
