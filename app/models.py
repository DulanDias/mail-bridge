from pydantic import BaseModel, EmailStr
from typing import List, Optional

class MailboxConfig(BaseModel):
    email: EmailStr
    imap_server: str
    smtp_server: str
    password: str  # Stored securely in Redis

class EmailSendRequest(BaseModel):
    to: List[EmailStr]
    cc: Optional[List[EmailStr]] = []
    bcc: Optional[List[EmailStr]] = []
    subject: str
    body: str
    attachments: Optional[List[str]] = None  # Paths to attachments
