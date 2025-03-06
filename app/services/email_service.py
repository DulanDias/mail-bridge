import smtplib
from app.services.celery_worker import celery
import imaplib
import aiosmtplib
from email.message import EmailMessage
from app.models import MailboxConfig
from app.services.redis_service import get_mailbox_config

@celery.task
def check_new_emails(mailbox_email: str):
    """ Background Task: Fetch New Emails """
    config = get_mailbox_config(mailbox_email)
    imap = imaplib.IMAP4_SSL(config["imap_server"])
    imap.login(config["email"], config["password"])
    imap.select("INBOX")
    _, messages = imap.search(None, "UNSEEN")
    email_ids = messages[0].split()
    return {"unread_count": len(email_ids)}

@celery.task
def send_email_task(mailbox_email: str, email_data):
    """ Background Task: Send Email via SMTP """
    config = get_mailbox_config(mailbox_email)
    msg = EmailMessage()
    msg["From"] = config["email"]
    msg["To"] = ", ".join(email_data.to)
    msg["CC"] = ", ".join(email_data.cc)
    msg["BCC"] = ", ".join(email_data.bcc)
    msg["Subject"] = email_data.subject
    msg.set_content(email_data.body)

    return aiosmtplib.send(msg, hostname=config["smtp_server"], port=587, username=config["email"], password=config["password"])

def validate_mailbox(config: MailboxConfig):
    """ Validate IMAP/SMTP connection """

    # Validate IMAP (incoming mail)
    try:
        imap = imaplib.IMAP4_SSL(config.imap_server)
        imap.login(config.email, config.password)
        imap.select("INBOX")
        imap.logout()
    except Exception as e:
        return False, f"IMAP Validation Failed: {str(e)}"

    # Validate SMTP (outgoing mail)
    try:
        smtp = smtplib.SMTP(config.smtp_server, 587)
        smtp.starttls()
        smtp.login(config.email, config.password)
        smtp.quit()
    except Exception as e:
        return False, f"SMTP Validation Failed: {str(e)}"

    return True, None
