import imaplib
import aiosmtplib
from email.message import EmailMessage
from app.services.redis_service import get_mailbox_config

def get_emails(mailbox_email: str, page: int, limit: int):
    """ Fetch emails from IMAP """
    config = get_mailbox_config(mailbox_email)
    imap = imaplib.IMAP4_SSL(config["imap_server"])
    imap.login(config["email"], config["password"])
    imap.select("INBOX")

    _, messages = imap.search(None, "ALL")
    email_ids = messages[0].split()[-(page * limit):-(page - 1) * limit]
    return {"emails": [eid.decode() for eid in email_ids]}

async def send_email(mailbox_email: str, email_data):
    """ Send an email via SMTP """
    config = get_mailbox_config(mailbox_email)

    msg = EmailMessage()
    msg["From"] = config["email"]
    msg["To"] = ", ".join(email_data.to)
    msg["CC"] = ", ".join(email_data.cc)
    msg["BCC"] = ", ".join(email_data.bcc)
    msg["Subject"] = email_data.subject
    msg.set_content(email_data.body)

    await aiosmtplib.send(msg, hostname=config["smtp_server"], port=587, username=config["email"], password=config["password"])
    return {"message": "Email sent successfully"}
