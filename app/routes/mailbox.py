import base64
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Query
from typing import List, Optional
from app.services import email_service, redis_service
from app.models import MailboxConfig

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
async def send_email(
    mailbox_email: str = Form(...),
    from_name: Optional[str] = Form(None),
    to: List[str] = Form(...),
    cc: Optional[List[str]] = Form([]),
    bcc: Optional[List[str]] = Form([]),
    subject: str = Form(...),
    body: str = Form(...),
    content_type: str = Form("html"),  # Default to "html"
    attachments: Optional[List[UploadFile]] = File(None)  # Optional attachments
):
    """ Send an email via SMTP with a selectable content type """

    try:
        # Process attachments
        attachments_data = []
        if attachments:
            for file in attachments:
                file_content = await file.read()  # Read file data
                encoded_content = base64.b64encode(file_content).decode("utf-8")  # Convert to base64
                attachments_data.append({
                    "filename": file.filename,
                    "content": encoded_content,
                    "content_type": file.content_type
                })

        email_data = {
            "from_name": from_name if from_name else mailbox_email,
            "to": to,
            "cc": cc,
            "bcc": bcc,
            "subject": subject,
            "body": body,
            "content_type": content_type.lower(),  # Normalize to lowercase
            "attachments": attachments_data
        }

        # Trigger Celery background task
        email_service.send_email_task.delay(mailbox_email, email_data)

        return {"message": "Email is being sent in the background"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    
@router.post("/delete")
async def delete_email(
    mailbox_email: str = Query(..., description="Email address of the mailbox"),
    email_id: str = Query(..., description="ID of the email to be deleted")
):
    """ Delete an email (move to Trash) """
    return email_service.delete_email(mailbox_email, email_id)

@router.post("/mark-read")
async def mark_email_as_read(mailbox_email: str, email_id: str):
    """ Mark an email as read """
    return {"message": f"Email {email_id} marked as read"}

@router.post("/mark-unread")
async def mark_email_as_unread(mailbox_email: str, email_id: str):
    """ Mark an email as unread """
    return {"message": f"Email {email_id} marked as unread"}

@router.post("/archive")
async def archive_email(mailbox_email: str, email_id: str):
    """ Move an email to Archive folder """
    return {"message": f"Email {email_id} archived"}

@router.get("/full-email/{email_id}")
async def fetch_full_email(mailbox_email: str, email_id: str):
    """ Fetch the full content of an email including attachments """
    return email_service.get_full_email(mailbox_email, email_id)

@router.get("/folder-emails")
async def fetch_emails_by_folder(mailbox_email: str, folder: str, page: int = 1, limit: int = 20):
    """ Fetch emails from Sent, Trash, or Archive folders with pagination """
    return email_service.get_emails_by_folder(mailbox_email, folder, page, limit)