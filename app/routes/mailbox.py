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
    return email_service.get_full_email_from_inbox(mailbox_email, email_id)

### FETCH EMAILS BY FOLDER ###
@router.get("/emails/inbox")
async def fetch_inbox(mailbox_email: str, page: int = 1, limit: int = 20):
    """ Fetch emails from Inbox """
    return email_service.get_emails_by_folder(mailbox_email, "INBOX", page, limit)

@router.get("/emails/trash")
async def fetch_trash(mailbox_email: str, page: int = 1, limit: int = 20):
    """ Fetch emails from Trash """
    return email_service.get_emails_by_folder(mailbox_email, "Trash", page, limit)

@router.get("/emails/spam")
async def fetch_spam(mailbox_email: str, page: int = 1, limit: int = 20):
    """ Fetch emails from Spam """
    return email_service.get_emails_by_folder(mailbox_email, "Spam", page, limit)

@router.get("/emails/drafts")
async def fetch_drafts(mailbox_email: str, page: int = 1, limit: int = 20):
    """ Fetch emails from Drafts """
    return email_service.get_emails_by_folder(mailbox_email, "Drafts", page, limit)

@router.get("/emails/sent")
async def fetch_sent(mailbox_email: str, page: int = 1, limit: int = 20):
    """ Fetch emails from Sent """
    return email_service.get_emails_by_folder(mailbox_email, "Sent", page, limit)

@router.get("/emails/archive")
async def fetch_archive(mailbox_email: str, page: int = 1, limit: int = 20):
    """ Fetch emails from Archive """
    return email_service.get_emails_by_folder(mailbox_email, "Archive", page, limit)

### DELETE EMAIL (MOVE TO TRASH FIRST) ###
@router.post("/delete")
async def delete_email(mailbox_email: str, email_id: str):
    """ Move email to Trash first, then permanently delete if already in Trash """
    return email_service.delete_email(mailbox_email, email_id)

@router.delete("/emails/trash/delete/{email_id}")
async def delete_email_from_trash(mailbox_email: str, email_id: str):
    """ Permanently delete a specific email from Trash """
    return email_service.delete_email_from_trash(mailbox_email, email_id)

### MOVE EMAIL BETWEEN FOLDERS ###
@router.post("/emails/move")
async def move_email(mailbox_email: str, email_id: str, from_folder: str, to_folder: str):
    """ Move email from one folder to another """
    return email_service.move_email(mailbox_email, email_id, from_folder, to_folder)

@router.post("/emails/trash/empty")
async def empty_trash(mailbox_email: str):
    """ Permanently delete all emails in Trash """
    return email_service.empty_trash(mailbox_email)

@router.get("/emails/{folder}/full-email/{email_id}")
async def fetch_full_email_from_folder(mailbox_email: str, folder: str, email_id: str):
    """ Fetch full email content including attachments from any folder """
    return email_service.get_full_email_from_folder(mailbox_email, email_id, folder)

@router.post("/emails/drafts/save")
async def save_draft(mailbox_email: str, email_data: dict):
    """ Save an email as a draft """
    return email_service.save_draft(mailbox_email, email_data)

@router.get("/emails/drafts/{email_id}")
async def fetch_draft(mailbox_email: str, email_id: str):
    """ Fetch a saved draft """
    return email_service.get_draft(mailbox_email, email_id)

@router.post("/emails/reply/{email_id}")
async def reply_email(mailbox_email: str, email_id: str, email_data: dict):
    """ Reply to an email """
    return email_service.reply_to_email(mailbox_email, email_id, email_data)
