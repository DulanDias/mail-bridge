from fastapi import APIRouter, HTTPException
from app.services import email_service

router = APIRouter()

@router.post("/validate")
async def validate_mailbox_connection(mailbox_email: str):
    """ Validate IMAP/SMTP connection for a mailbox """
    success, error = email_service.validate_mailbox(mailbox_email)
    if not success:
        raise HTTPException(status_code=400, detail=error)
    return {"message": "Mailbox connection is valid"}
