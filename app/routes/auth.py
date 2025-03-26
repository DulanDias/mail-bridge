from fastapi import APIRouter, HTTPException
from app.models import MailboxConfig
from app.services.jwt_service import generate_jwt, decode_jwt  # Updated import
from app.services.email_service import validate_mailbox

router = APIRouter()

@router.post("/validate")
async def validate_mailbox_connection(config: MailboxConfig):
    """ Validate IMAP/SMTP connection for a mailbox """
    success, error = validate_mailbox(config)
    if not success:
        raise HTTPException(status_code=400, detail=error)
    return {"message": "Mailbox connection is valid"}

@router.post("/login")
async def login(config: MailboxConfig):
    """ Authenticate user and issue a JWT token """
    success, error = validate_mailbox(config)
    if not success:
        raise HTTPException(status_code=400, detail=error)
    token = generate_jwt(config.email, config.password)
    return {"token": token}

@router.get("/decode-token")
async def decode_token(token: str):
    """ Decode JWT token to retrieve credentials (for testing purposes) """
    try:
        email, password = decode_jwt(token)
        return {"email": email, "password": password}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
