from fastapi import APIRouter, HTTPException
from app.models import MailboxConfig
from app.services.jwt_service import generate_jwt, generate_refresh_token, decode_refresh_token
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
    """ Authenticate user and issue JWT and refresh tokens """
    # Validate credentials directly
    success, error = validate_mailbox(config)
    if not success:
        raise HTTPException(status_code=401, detail=error)
    
    # Generate tokens
    jwt_token = generate_jwt(
        config.email,
        config.password,
        config.imap_server,
        config.smtp_server,
        config.imap_port,
        config.smtp_port
    )
    refresh_token = generate_refresh_token(
        config.email,
        config.password,
        config.imap_server,
        config.smtp_server,
        config.imap_port,
        config.smtp_port
    )
    logging.debug(f"Issued JWT token: {jwt_token}")
    logging.debug(f"Issued Refresh Token: {refresh_token}")
    return {"jwt_token": jwt_token, "refresh_token": refresh_token}

@router.post("/refresh-token")
async def refresh_token(refresh_token: str):
    """ Refresh JWT token using a valid refresh token """
    try:
        # Decode the refresh token to extract its payload
        email, password, imap_server, smtp_server, imap_port, smtp_port = decode_refresh_token(refresh_token)
        
        # Generate a new JWT token using the decoded values
        jwt_token = generate_jwt(
            email,
            password,
            imap_server,
            smtp_server,
            imap_port,
            smtp_port
        )
        return {"jwt_token": jwt_token}
    except Exception as e:
        logging.error(f"Error refreshing token: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

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
