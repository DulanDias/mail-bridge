import base64
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Header
from typing import List, Optional
from app.services import email_service
from app.services.jwt_service import decode_jwt
from app.models import DraftEmail, MailboxConfig  # Add MailboxConfig to the imports
from fastapi.openapi.models import APIKey

router = APIRouter()

def extract_mailbox_token(authorization: str):
    """Extract and decode the mailbox token from the Authorization header."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    token = authorization.split(" ")[1]
    return decode_jwt(token)

### MAILBOX CONFIGURATION ###
@router.post("/config")
async def configure_mailbox(config: MailboxConfig):
    """ Store mailbox configuration securely """
    # This endpoint may no longer be needed if JWT is used for all configurations.
    # Consider removing or refactoring this endpoint.
    pass

@router.post("/validate")
async def validate_mailbox_connection(mailbox_token: str):
    """ Validate IMAP/SMTP connection using mailbox_token """
    success, error = email_service.validate_mailbox(mailbox_token)
    if not success:
        raise HTTPException(status_code=400, detail=error)
    return {"message": "Mailbox connection is valid"}

### EMAIL SENDING ###
@router.post(
    "/send",
    summary="Send an email",
    description="Send an email via SMTP with optional attachments.",
    responses={
        200: {"description": "Email is being sent in the background"},
        400: {"description": "Invalid input or missing fields"},
    },
)
async def send_email(
    authorization: str = Header(
        ...,
        description="Bearer token for authentication",
        example="Bearer <your_jwt_token>"
    ),
    from_name: Optional[str] = Form(None),
    to: List[str] = Form(..., description="List of recipient email addresses"),
    cc: Optional[List[str]] = Form([], description="List of CC email addresses"),
    bcc: Optional[List[str]] = Form([], description="List of BCC email addresses"),
    subject: str = Form(..., description="Subject of the email"),
    body: str = Form(..., description="Body of the email"),
    content_type: str = Form("html", description="Content type of the email (html or plain)"),
    attachments: Optional[List[UploadFile]] = File(
        None,
        description="List of file attachments. Each file should be uploaded as a multipart/form-data file."
    ),
    read_receipt: bool = Form(False, description="Request a read receipt"),
    read_receipt_email: Optional[str] = Form(None, description="Email address for read receipt notifications"),
):
    """Send an email via SMTP."""
    email, password, imap_server, smtp_server, imap_port, smtp_port = extract_mailbox_token(authorization)
    attachments_data = []
    if attachments:
        for file in attachments:
            file_content = await file.read()
            encoded_content = base64.b64encode(file_content).decode("utf-8")
            attachments_data.append({
                "filename": file.filename,
                "content": encoded_content,
                "content_type": file.content_type
            })

    email_data = {
        "from_name": from_name if from_name else email,
        "to": to,
        "cc": cc,
        "bcc": bcc,
        "subject": subject,
        "body": body,
        "content_type": content_type.lower(),
        "attachments": attachments_data,
        "read_receipt": read_receipt,
        "read_receipt_email": read_receipt_email
    }

    email_service.send_email_task.delay(authorization.split(" ")[1], email_data)
    return {"message": "Email is being sent in the background"}

### EMAIL FETCHING ###
@router.get("/emails")
async def fetch_emails(authorization: str = Header(...), page: int = 1, limit: int = 20):
    """Fetch emails for a specific mailbox."""
    mailbox_token = authorization.split(" ")[1]
    emails = email_service.get_emails(mailbox_token, page, limit)
    for email in emails.get("emails", []):
        email["to"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "To")
        email["cc"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "Cc")
        email["bcc"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "Bcc")
        email["flags"] = email_service.get_email_flags(mailbox_token, email["email_id"])
    return emails

@router.get("/full-email/{email_id}")
async def fetch_full_email(email_id: str, authorization: str = Header(...)):
    """Fetch the full content of an email including attachments."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.get_full_email_from_inbox(mailbox_token, email_id)

@router.get("/emails/{folder}/full-email/{email_id}")
async def fetch_full_email_from_folder(folder: str, email_id: str, authorization: str = Header(...)):
    """Fetch full email content including attachments from any folder."""
    mailbox_token = authorization.split(" ")[1]
    email = email_service.get_full_email_from_folder(mailbox_token, email_id, folder)
    email["to"] = email_service.get_email_recipients(mailbox_token, email_id, "To")
    email["cc"] = email_service.get_email_recipients(mailbox_token, email_id, "Cc")
    email["bcc"] = email_service.get_email_recipients(mailbox_token, email_id, "Bcc")
    email["flags"] = email_service.get_email_flags(mailbox_token, email_id)
    return email

### EMAIL MANAGEMENT ###
@router.post("/delete")
async def delete_email(authorization: str = Header(...), email_id: str = Form(...)):
    """Delete an email (move to Trash)."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.delete_email(mailbox_token, email_id)

@router.delete("/emails/trash/delete/{email_id}")
async def delete_email_from_trash(email_id: str, authorization: str = Header(...)):
    """Permanently delete a specific email from Trash."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.delete_email_from_trash(mailbox_token, email_id)

@router.post("/emails/move")
async def move_email(
    authorization: str = Header(...),
    email_id: str = Form(...),
    from_folder: str = Form(...),
    to_folder: str = Form(...)
):
    """Move email from one folder to another."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.move_email(mailbox_token, email_id, from_folder, to_folder)

@router.post("/emails/trash/empty")
async def empty_trash(authorization: str = Header(...)):
    """Permanently delete all emails in Trash."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.empty_trash(mailbox_token)

@router.post("/mark-read")
async def mark_email_as_read(authorization: str = Header(...), email_id: str = Form(...)):
    """Mark an email as read."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.mark_email_as_read(mailbox_token, email_id)

@router.post("/mark-unread")
async def mark_email_as_unread(authorization: str = Header(...), email_id: str = Form(...)):
    """Mark an email as unread."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.mark_email_as_unread(mailbox_token, email_id)

@router.post("/emails/star/{email_id}")
async def star_email(email_id: str, authorization: str = Header(...)):
    """Star an email."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.star_email(mailbox_token, email_id)

@router.post("/emails/unstar/{email_id}")
async def unstar_email(email_id: str, authorization: str = Header(...)):
    """Unstar an email."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.unstar_email(mailbox_token, email_id)

### EMAIL FOLDERS ###
@router.get("/emails/inbox")
async def fetch_inbox(authorization: str = Header(...), page: int = 1, limit: int = 20):
    """Fetch emails from Inbox."""
    mailbox_token = authorization.split(" ")[1]
    emails = email_service.get_emails_by_folder(mailbox_token, "INBOX", page, limit)
    for email in emails.get("emails", []):
        email["to"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "To")
        email["cc"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "Cc")
        email["bcc"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "Bcc")
        email["flags"] = email_service.get_email_flags(mailbox_token, email["email_id"])
    return emails

@router.get("/emails/trash")
async def fetch_trash(authorization: str = Header(...), page: int = 1, limit: int = 20):
    """Fetch emails from Trash."""
    mailbox_token = authorization.split(" ")[1]
    emails = email_service.get_emails_by_folder(mailbox_token, "Trash", page, limit)
    for email in emails.get("emails", []):
        email["to"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "To")
        email["cc"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "Cc")
        email["bcc"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "Bcc")
        email["flags"] = email_service.get_email_flags(mailbox_token, email["email_id"])
    return emails

@router.get("/emails/spam")
async def fetch_spam(authorization: str = Header(...), page: int = 1, limit: int = 20):
    """Fetch emails from Spam."""
    mailbox_token = authorization.split(" ")[1]
    emails = email_service.get_emails_by_folder(mailbox_token, "Spam", page, limit)
    for email in emails.get("emails", []):
        email["to"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "To")
        email["cc"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "Cc")
        email["bcc"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "Bcc")
        email["flags"] = email_service.get_email_flags(mailbox_token, email["email_id"])
    return emails

@router.get("/emails/drafts")
async def fetch_drafts(authorization: str = Header(...), page: int = 1, limit: int = 20):
    """Fetch emails from Drafts."""
    mailbox_token = authorization.split(" ")[1]
    emails = email_service.get_emails_by_folder(mailbox_token, "Drafts", page, limit)
    for email in emails.get("emails", []):
        email["to"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "To")
        email["cc"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "Cc")
        email["bcc"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "Bcc")
        email["flags"] = email_service.get_email_flags(mailbox_token, email["email_id"])
    return emails

@router.get("/emails/sent")
async def fetch_sent(authorization: str = Header(...), page: int = 1, limit: int = 20):
    """Fetch emails from Sent."""
    mailbox_token = authorization.split(" ")[1]
    emails = email_service.get_emails_by_folder(mailbox_token, "Sent", page, limit)
    for email in emails.get("emails", []):
        email["to"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "To")
        email["cc"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "Cc")
        email["bcc"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "Bcc")
        email["flags"] = email_service.get_email_flags(mailbox_token, email["email_id"])
    return emails

@router.get("/emails/archive")
async def fetch_archive(authorization: str = Header(...), page: int = 1, limit: int = 20):
    """Fetch emails from Archive."""
    mailbox_token = authorization.split(" ")[1]
    emails = email_service.get_emails_by_folder(mailbox_token, "Archive", page, limit)
    for email in emails.get("emails", []):
        email["to"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "To")
        email["cc"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "Cc")
        email["bcc"] = email_service.get_email_recipients(mailbox_token, email["email_id"], "Bcc")
        email["flags"] = email_service.get_email_flags(mailbox_token, email["email_id"])
    return emails

@router.get("/emails/starred")
async def fetch_starred_emails(authorization: str = Header(...), page: int = 1, limit: int = 20):
    """Fetch starred emails."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.get_starred_emails(mailbox_token, page, limit)

@router.get("/emails/{folder}/count")
async def get_email_count(folder: str, authorization: str = Header(...)):
    """Get the total number of emails in a specified folder."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.get_email_count(mailbox_token, folder)

### EMAIL DRAFTS ###
@router.post("/emails/drafts/save")
async def save_draft(draft: DraftEmail, authorization: str = Header(...)):
    """Save an email as a draft."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.save_draft(mailbox_token, draft.dict())

@router.get("/emails/drafts/{email_id}")
async def fetch_draft(email_id: str, authorization: str = Header(...)):
    """Fetch a saved draft."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.get_draft(mailbox_token, email_id)

@router.put("/emails/drafts/{email_id}")
async def update_draft(email_id: str, draft: DraftEmail, authorization: str = Header(...)):
    """Update a saved draft."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.update_draft(mailbox_token, email_id, draft.dict())

@router.delete("/emails/drafts/delete/{email_id}")
async def delete_draft(email_id: str, authorization: str = Header(...)):
    """Delete a saved draft."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.delete_draft(mailbox_token, email_id)

### EMAIL ACTIONS ###
@router.post("/emails/reply/{email_id}")
async def reply_email(email_id: str, email_data: dict, authorization: str = Header(...)):
    """Reply to an email."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.reply_to_email(mailbox_token, email_id, email_data)

@router.post("/emails/forward/{email_id}")
async def forward_email(email_id: str, email_data: dict, authorization: str = Header(...)):
    """Forward an email."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.forward_email(mailbox_token, email_id, email_data)

@router.post("emails/reply-all/{email_id}")
async def reply_all(email_id: str, email_data: dict, authorization: str = Header(...)):
    """Reply to all recipients of an email."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.reply_all(mailbox_token, email_id, email_data)

@router.post("/emails/archive/{email_id}")
async def archive_email(email_id: str, authorization: str = Header(...)):
    """Move an email to Archive folder."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.move_email(mailbox_token, email_id, "INBOX", "Archive")

### EMAIL SEARCH AND FILTER ###
@router.get("/emails/search")
async def search_emails(query: str, page: int = 1, limit: int = 20, authorization: str = Header(...)):
    """Search emails based on a query."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.search_emails(mailbox_token, query, page, limit)

@router.get("/emails/filter")
async def filter_emails(filter_type: str, page: int = 1, limit: int = 20, authorization: str = Header(...)):
    """Filter emails based on a filter type."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.filter_emails(mailbox_token, filter_type, page, limit)

@router.get("/emails/unread/count")
async def get_unread_email_count(authorization: str = Header(...)):
    """Get the count of unread emails."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.get_unread_email_count(mailbox_token)

### EMAIL ATTACHMENTS ###
@router.get("/emails/attachments/{email_id}")
async def fetch_email_attachments(email_id: str, authorization: str = Header(...)):
    """Fetch attachments of a specific email."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.get_email_attachments(mailbox_token, email_id)

@router.get("/emails/attachment/{email_id}/{attachment_id}")
async def fetch_email_attachment(email_id: str, attachment_id: str, authorization: str = Header(...)):
    """Fetch a specific attachment of an email."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.get_email_attachment(mailbox_token, email_id, attachment_id)

@router.get("/emails/attachment/download/{email_id}/{attachment_id}")
async def download_email_attachment(email_id: str, attachment_id: str, authorization: str = Header(...)):
    """Download a specific attachment of an email."""
    mailbox_token = authorization.split(" ")[1]
    return email_service.download_email_attachment(mailbox_token, email_id, attachment_id)

@router.post("/emails/{folder}/mark-read")
async def mark_email_as_read_in_folder(email_id: str, folder: str, authorization: str = Header(...)):
    """ Mark an email as read in a specific folder """
    mailbox_token = authorization.split(" ")[1]
    return email_service.set_email_flag(mailbox_token, email_id, folder, "\\Seen", True)

@router.post("/emails/{folder}/mark-unread")
async def mark_email_as_unread_in_folder(email_id: str, folder: str, authorization: str = Header(...)):
    """ Mark an email as unread in a specific folder """
    mailbox_token = authorization.split(" ")[1]
    return email_service.set_email_flag(mailbox_token, email_id, folder, "\\Seen", False)

@router.post("/emails/{folder}/star")
async def star_email_in_folder(email_id: str, folder: str, authorization: str = Header(...)):
    """ Star an email in a specific folder """
    mailbox_token = authorization.split(" ")[1]
    return email_service.set_email_flag(mailbox_token, email_id, folder, "\\Flagged", True)

@router.post("/emails/{folder}/unstar")
async def unstar_email_in_folder(email_id: str, folder: str, authorization: str = Header(...)):
    """ Unstar an email in a specific folder """
    mailbox_token = authorization.split(" ")[1]
    return email_service.set_email_flag(mailbox_token, email_id, folder, "\\Flagged", False)