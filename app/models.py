from pydantic import BaseModel, EmailStr
from typing import List, Optional

class MailboxConfig(BaseModel):
    email: EmailStr
    imap_server: str
    smtp_server: str
    imap_port: int = 993  # Default IMAP port
    smtp_port: int = 587  # Default SMTP port
    password: str  # Used for authentication, securely managed via JWT

class EmailSendRequest(BaseModel):
    to: List[EmailStr]
    cc: Optional[List[EmailStr]] = []
    bcc: Optional[List[EmailStr]] = []
    subject: str
    body: str
    attachments: Optional[List[str]] = None  # Paths to attachments
