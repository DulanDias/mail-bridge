from fastapi import APIRouter
from app.services import email_service, redis_service
from app.models import MailboxConfig, EmailSendRequest

router = APIRouter()

@router.post("/config")
async def configure_mailbox(config: MailboxConfig):
    """ Store mailbox configuration securely in Redis """
    redis_service.store_mailbox_config(config)
    return {"message": "Mailbox configured successfully"}

@router.get("/emails")
async def fetch_emails(mailbox_email: str, page: int = 1, limit: int = 20):
    """ Fetch emails for a specific mailbox """
    return email_service.get_emails(mailbox_email, page, limit)

@router.post("/send")
async def send_email(mailbox_email: str, email_data: EmailSendRequest):
    """ Send an email via SMTP """
    return email_service.send_email(mailbox_email, email_data)

@router.post("/delete")
async def delete_email(mailbox_email: str, email_id: str):
    """ Delete an email (move to trash) """
    return email_service.delete_email(mailbox_email, email_id)

@router.post("/mark-read")
async def mark_email_as_read(mailbox_email: str, email_id: str):
    """ Mark an email as read """
    return email_service.mark_as_read(mailbox_email, email_id)

@router.post("/mark-unread")
async def mark_email_as_unread(mailbox_email: str, email_id: str):
    """ Mark an email as unread """
    return email_service.mark_as_unread(mailbox_email, email_id)

@router.post("/archive")
async def archive_email(mailbox_email: str, email_id: str):
    """ Move an email to Archive folder """
    return email_service.archive_email(mailbox_email, email_id)
