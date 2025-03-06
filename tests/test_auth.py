from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_validate_mailbox():
    response = client.post("/api/v1/auth/validate", json={"mailbox_email": "test@example.com"})
    assert response.status_code in [200, 400]  # Depends on whether validation succeeds
