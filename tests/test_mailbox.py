from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_fetch_emails():
    response = client.get("/api/v1/mailbox/emails?mailbox_email=test@example.com")
    assert response.status_code == 200
    assert "emails" in response.json()
