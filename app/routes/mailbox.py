import base64
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Query
from typing import List, Optional
from app.services import email_service, redis_service
from app.models import MailboxConfig

router = APIRouter()

### MAILBOX CONFIGURATION ###
@router.post("/config")
async def configure_mailbox(config: MailboxConfig):
    """
    Store mailbox configuration securely in Redis.
    
    Example:
    {
        "email": "user@example.com",
        "imap_server": "imap.example.com",
        "smtp_server": "smtp.example.com",
        "password": "password"
    }
    """
    redis_service.store_mailbox_config(config)
    return {"message": "Mailbox configured successfully"}

### EMAIL SENDING ###
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
    attachments: Optional[List[UploadFile]] = File(None),  # Optional attachments
    read_receipt: bool = Form(False),  # Optional read receipt request
    read_receipt_email: Optional[str] = Form(None)  # Optional email for read receipts
):
    """
    Send an email via SMTP with a selectable content type and optional read receipt.
    
    Example:
    {
        "mailbox_email": "user@example.com",
        "from_name": "User",
        "to": ["recipient@example.com"],
        "cc": ["cc@example.com"],
        "bcc": ["bcc@example.com"],
        "subject": "Test Email",
        "body": "<h1>Hello</h1>",
        "content_type": "html",
        "attachments": [],
        "read_receipt": true,
        "read_receipt_email": "readreceipt@example.com"
    }
    """
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
            "attachments": attachments_data,
            "read_receipt": read_receipt,  # Include read receipt request
            "read_receipt_email": read_receipt_email  # Include read receipt email
        }

        # Trigger Celery background task
        email_service.send_email_task.delay(mailbox_email, email_data)

        return {"message": "Email is being sent in the background"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

### EMAIL FETCHING ###
@router.get("/emails")
async def fetch_emails(mailbox_email: str, page: int = 1, limit: int = 20):
    """
    Fetch emails for a specific mailbox.
    
    Example:
    GET /emails?mailbox_email=user@example.com&page=1&limit=20
    """
    emails = email_service.get_emails(mailbox_email, page, limit)
    for email in emails.get("emails", []):
        email["to"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "To")
        email["cc"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "Cc")
        email["bcc"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "Bcc")
        email["flags"] = email_service.get_email_flags(mailbox_email, email["email_id"])
    return emails

@router.get("/full-email/{email_id}")
async def fetch_full_email(mailbox_email: str, email_id: str):
    """
    Fetch the full content of an email including attachments.
    
    Example:
    GET /full-email/12345?mailbox_email=user@example.com
    """
    return email_service.get_full_email_from_inbox(mailbox_email, email_id)

@router.get("/emails/{folder}/full-email/{email_id}")
async def fetch_full_email_from_folder(mailbox_email: str, folder: str, email_id: str):
    """
    Fetch full email content including attachments from any folder.
    
    Example:
    GET /emails/inbox/full-email/12345?mailbox_email=user@example.com
    """
    email = email_service.get_full_email_from_folder(mailbox_email, email_id, folder)
    email["to"] = email_service.get_email_recipients(mailbox_email, email_id, "To")
    email["cc"] = email_service.get_email_recipients(mailbox_email, email_id, "Cc")
    email["bcc"] = email_service.get_email_recipients(mailbox_email, email_id, "Bcc")
    email["flags"] = email_service.get_email_flags(mailbox_email, email_id)
    return email

### EMAIL MANAGEMENT ###
@router.post("/delete")
async def delete_email(
    mailbox_email: str = Query(..., description="Email address of the mailbox"),
    email_id: str = Query(..., description="ID of the email to be deleted")
):
    """
    Delete an email (move to Trash).
    
    Example:
    POST /delete?mailbox_email=user@example.com&email_id=12345
    """
    return email_service.delete_email(mailbox_email, email_id)

@router.delete("/emails/trash/delete/{email_id}")
async def delete_email_from_trash(mailbox_email: str, email_id: str):
    """
    Permanently delete a specific email from Trash.
    
    Example:
    DELETE /emails/trash/delete/12345?mailbox_email=user@example.com
    """
    return email_service.delete_email_from_trash(mailbox_email, email_id)

@router.post("/emails/move")
async def move_email(mailbox_email: str, email_id: str, from_folder: str, to_folder: str):
    """
    Move email from one folder to another.
    
    Example:
    POST /emails/move?mailbox_email=user@example.com&email_id=12345&from_folder=INBOX&to_folder=Archive
    """
    return email_service.move_email(mailbox_email, email_id, from_folder, to_folder)

@router.post("/emails/trash/empty")
async def empty_trash(mailbox_email: str):
    """
    Permanently delete all emails in Trash.
    
    Example:
    POST /emails/trash/empty?mailbox_email=user@example.com
    """
    return email_service.empty_trash(mailbox_email)

@router.post("/mark-read")
async def mark_email_as_read(mailbox_email: str, email_id: str):
    """
    Mark an email as read.
    
    Example:
    POST /mark-read?mailbox_email=user@example.com&email_id=12345
    """
    return email_service.mark_email_as_read(mailbox_email, email_id)

@router.post("/mark-unread")
async def mark_email_as_unread(mailbox_email: str, email_id: str):
    """
    Mark an email as unread.
    
    Example:
    POST /mark-unread?mailbox_email=user@example.com&email_id=12345
    """
    return email_service.mark_email_as_unread(mailbox_email, email_id)

@router.post("/emails/star/{email_id}")
async def star_email(mailbox_email: str, email_id: str):
    """
    Star an email.
    
    Example:
    POST /emails/star/12345?mailbox_email=user@example.com
    """
    return email_service.star_email(mailbox_email, email_id)

@router.post("/emails/unstar/{email_id}")
async def unstar_email(mailbox_email: str, email_id: str):
    """
    Unstar an email.
    
    Example:
    POST /emails/unstar/12345?mailbox_email=user@example.com
    """
    return email_service.unstar_email(mailbox_email, email_id)

### EMAIL FOLDERS ###
@router.get("/emails/inbox")
async def fetch_inbox(mailbox_email: str, page: int = 1, limit: int = 20):
    """
    Fetch emails from Inbox.
    
    Example:
    GET /emails/inbox?mailbox_email=user@example.com&page=1&limit=20
    """
    emails = email_service.get_emails_by_folder(mailbox_email, "INBOX", page, limit)
    for email in emails.get("emails", []):
        email["to"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "To")
        email["cc"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "Cc")
        email["bcc"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "Bcc")
        email["flags"] = email_service.get_email_flags(mailbox_email, email["email_id"])
    return emails

@router.get("/emails/trash")
async def fetch_trash(mailbox_email: str, page: int = 1, limit: int = 20):
    """
    Fetch emails from Trash.
    
    Example:
    GET /emails/trash?mailbox_email=user@example.com&page=1&limit=20
    """
    emails = email_service.get_emails_by_folder(mailbox_email, "Trash", page, limit)
    for email in emails.get("emails", []):
        email["to"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "To")
        email["cc"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "Cc")
        email["bcc"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "Bcc")
        email["flags"] = email_service.get_email_flags(mailbox_email, email["email_id"])
    return emails

@router.get("/emails/spam")
async def fetch_spam(mailbox_email: str, page: int = 1, limit: int = 20):
    """
    Fetch emails from Spam.
    
    Example:
    GET /emails/spam?mailbox_email=user@example.com&page=1&limit=20
    """
    emails = email_service.get_emails_by_folder(mailbox_email, "Spam", page, limit)
    for email in emails.get("emails", []):
        email["to"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "To")
        email["cc"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "Cc")
        email["bcc"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "Bcc")
        email["flags"] = email_service.get_email_flags(mailbox_email, email["email_id"])
    return emails

@router.get("/emails/drafts")
async def fetch_drafts(mailbox_email: str, page: int = 1, limit: int = 20):
    """
    Fetch emails from Drafts.
    
    Example:
    GET /emails/drafts?mailbox_email=user@example.com&page=1&limit=20
    """
    emails = email_service.get_emails_by_folder(mailbox_email, "Drafts", page, limit)
    for email in emails.get("emails", []):
        email["to"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "To")
        email["cc"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "Cc")
        email["bcc"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "Bcc")
        email["flags"] = email_service.get_email_flags(mailbox_email, email["email_id"])
    return emails

@router.get("/emails/sent")
async def fetch_sent(mailbox_email: str, page: int = 1, limit: int = 20):
    """
    Fetch emails from Sent.
    
    Example:
    GET /emails/sent?mailbox_email=user@example.com&page=1&limit=20
    """
    emails = email_service.get_emails_by_folder(mailbox_email, "Sent", page, limit)
    for email in emails.get("emails", []):
        email["to"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "To")
        email["cc"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "Cc")
        email["bcc"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "Bcc")
        email["flags"] = email_service.get_email_flags(mailbox_email, email["email_id"])
    return emails

@router.get("/emails/archive")
async def fetch_archive(mailbox_email: str, page: int = 1, limit: int = 20):
    """
    Fetch emails from Archive.
    
    Example:
    GET /emails/archive?mailbox_email=user@example.com&page=1&limit=20
    """
    emails = email_service.get_emails_by_folder(mailbox_email, "Archive", page, limit)
    for email in emails.get("emails", []):
        email["to"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "To")
        email["cc"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "Cc")
        email["bcc"] = email_service.get_email_recipients(mailbox_email, email["email_id"], "Bcc")
        email["flags"] = email_service.get_email_flags(mailbox_email, email["email_id"])
    return emails

@router.get("/emails/starred")
async def fetch_starred_emails(mailbox_email: str, page: int = 1, limit: int = 20):
    """
    Fetch starred emails.
    
    Example:
    GET /emails/starred?mailbox_email=user@example.com&page=1&limit=20
    """
    return email_service.get_starred_emails(mailbox_email, page, limit)

@router.get("/emails/{folder}/count")
async def get_email_count(mailbox_email: str, folder: str):
    """
    Get the total number of emails in a specified folder.
    
    Example:
    GET /emails/inbox/count?mailbox_email=user@example.com
    """
    return email_service.get_email_count(mailbox_email, folder)

### EMAIL DRAFTS ###
@router.post("/emails/drafts/save")
async def save_draft(mailbox_email: str, email_data: dict):
    """
    Save an email as a draft.
    
    Example:
    POST /emails/drafts/save
    {
        "mailbox_email": "user@example.com",
        "email_data": {
            "from_name": "User",
            "to": ["recipient@example.com"],
            "subject": "Draft Email",
            "body": "This is a draft email."
        }
    }
    """
    return email_service.save_draft(mailbox_email, email_data)

@router.get("/emails/drafts/{email_id}")
async def fetch_draft(mailbox_email: str, email_id: str):
    """
    Fetch a saved draft.
    
    Example:
    GET /emails/drafts/12345?mailbox_email=user@example.com
    """
    return email_service.get_draft(mailbox_email, email_id)

@router.put("/emails/drafts/{email_id}")
async def update_draft(mailbox_email: str, email_id: str, email_data: dict):
    """
    Update a saved draft.
    
    Example:
    PUT /emails/drafts/12345
    {
        "mailbox_email": "user@example.com",
        "email_data": {
            "from_name": "User",
            "to": ["recipient@example.com"],
            "subject": "Updated Draft Email",
            "body": "This is an updated draft email."
        }
    }
    """
    return email_service.update_draft(mailbox_email, email_id, email_data)

@router.delete("/emails/drafts/delete/{email_id}")
async def delete_draft(mailbox_email: str, email_id: str):
    """
    Delete a saved draft.
    
    Example:
    DELETE /emails/drafts/delete/12345?mailbox_email=user@example.com
    """
    return email_service.delete_draft(mailbox_email, email_id)

### EMAIL ACTIONS ###
@router.post("/emails/reply/{email_id}")
async def reply_email(mailbox_email: str, email_id: str, email_data: dict):
    """
    Reply to an email.
    
    Example:
    POST /emails/reply/12345
    {
        "mailbox_email": "user@example.com",
        "email_data": {
            "from_name": "User",
            "body": "This is a reply."
        }
    }
    """
    return email_service.reply_to_email(mailbox_email, email_id, email_data)

@router.post("/emails/forward/{email_id}")
async def forward_email(mailbox_email: str, email_id: str, email_data: dict):
    """
    Forward an email.
    
    Example:
    POST /emails/forward/12345
    {
        "mailbox_email": "user@example.com",
        "email_data": {
            "from_name": "User",
            "to": ["recipient@example.com"],
            "body": "This is a forwarded email."
        }
    }
    """
    return email_service.forward_email(mailbox_email, email_id, email_data)

@router.post("emails/reply-all/{email_id}")
async def reply_all(mailbox_email: str, email_id: str, email_data: dict):
    """
    Reply to all recipients of an email.
    
    Example:
    POST /emails/reply-all/12345
    {
        "mailbox_email": "user@example.com",
        "email_data": {
            "from_name": "User",
            "body": "This is a reply to all."
        }
    }
    """
    return email_service.reply_all(mailbox_email, email_id, email_data)

@router.post("/emails/archive/{email_id}")
async def archive_email(mailbox_email: str, email_id: str):
    """
    Move an email to Archive folder.
    
    Example:
    POST /emails/archive/12345?mailbox_email=user@example.com
    """
    return email_service.move_email(mailbox_email, email_id, "INBOX", "Archive")

### EMAIL SEARCH AND FILTER ###
@router.get("/emails/search")
async def search_emails(mailbox_email: str, query: str, page: int = 1, limit: int = 20):
    """
    Search emails based on a query.
    
    Example:
    GET /emails/search?mailbox_email=user@example.com&query=subject:test&page=1&limit=20
    """
    return email_service.search_emails(mailbox_email, query, page, limit)

@router.get("/emails/filter")
async def filter_emails(mailbox_email: str, filter_type: str, page: int = 1, limit: int = 20):
    """
    Filter emails based on a filter type.
    
    Example:
    GET /emails/filter?mailbox_email=user@example.com&filter_type=unread&page=1&limit=20
    """
    return email_service.filter_emails(mailbox_email, filter_type, page, limit)

@router.get("/emails/unread/count")
async def get_unread_email_count(mailbox_email: str):
    """
    Get the count of unread emails.
    
    Example:
    GET /emails/unread/count?mailbox_email=user@example.com
    """
    return email_service.get_unread_email_count(mailbox_email)

### EMAIL ATTACHMENTS ###
@router.get("/emails/attachments/{email_id}")
async def fetch_email_attachments(mailbox_email: str, email_id: str):
    """
    Fetch attachments of a specific email.
    
    Example:
    GET /emails/attachments/12345?mailbox_email=user@example.com
    """
    return email_service.get_email_attachments(mailbox_email, email_id)

@router.get("/emails/attachment/{email_id}/{attachment_id}")
async def fetch_email_attachment(mailbox_email: str, email_id: str, attachment_id: str):
    """
    Fetch a specific attachment of an email.
    
    Example:
    GET /emails/attachment/12345/attachment1?mailbox_email=user@example.com
    """
    return email_service.get_email_attachment(mailbox_email, email_id, attachment_id)

@router.get("/emails/attachment/download/{email_id}/{attachment_id}")
async def download_email_attachment(mailbox_email: str, email_id: str, attachment_id: str):
    """
    Download a specific attachment of an email.
    
    Example:
    GET /emails/attachment/download/12345/attachment1?mailbox_email=user@example.com
    """
    return email_service.download_email_attachment(mailbox_email, email_id, attachment_id)