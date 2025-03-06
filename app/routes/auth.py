from fastapi import APIRouter, HTTPException
from app.models import MailboxConfig
from app.services.email_service import validate_mailbox

router = APIRouter()

@router.post("/validate")
async def validate_mailbox_connection(config: MailboxConfig):
    """ Validate IMAP/SMTP connection for a mailbox """
    success, error = validate_mailbox(config)
    if not success:
        raise HTTPException(status_code=400, detail=error)
    return {"message": "Mailbox connection is valid"}
