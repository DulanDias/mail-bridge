from fastapi import APIRouter, HTTPException
from app.models import MailboxConfig
from app.services.jwt_service import generate_jwt
from app.services.email_service import validate_mailbox
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)

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
    # Validate credentials directly
    success, error = validate_mailbox(config)
    if not success:
        raise HTTPException(status_code=400, detail=error)
    
    # Generate a JWT token for future use
    token = generate_jwt(
        config.email,
        config.password,
        config.imap_server,
        config.smtp_server,
        config.imap_port,
        config.smtp_port
    )
    logging.debug(f"Issued JWT token: {token}")
    return {"token": token}

@router.get("/decode-token")
async def decode_token(token: str):
    """ Decode JWT token to retrieve credentials (for testing purposes) """
    try:
        # Unpack all six values returned by decode_jwt
        email, password, imap_server, smtp_server, imap_port, smtp_port = decode_jwt(token)
        logging.debug(f"Decoded token for email: {email}")
        return {
            "email": email,
            "password": password,
            "imap_server": imap_server,
            "smtp_server": smtp_server,
            "imap_port": imap_port,
            "smtp_port": smtp_port
        }
    except Exception as e:
        logging.error(f"Error decoding token: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
