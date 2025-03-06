import email
import smtplib
from app.services.celery_worker import celery
import imaplib
import aiosmtplib
from email.message import EmailMessage
from email.header import decode_header
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

def get_emails(mailbox_email: str, page: int = 1, limit: int = 20):
    """ Fetch emails from the mailbox using IMAP and return subject, sender, date, and partial email body """

    # Retrieve stored mailbox configuration
    config = get_mailbox_config(mailbox_email)

    try:
        # Connect to IMAP server
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])
        imap.select("INBOX")

        # Fetch all email IDs
        _, messages = imap.search(None, "ALL")
        email_ids = messages[0].split()

        # Paginate results
        start = max(0, len(email_ids) - (page * limit))
        end = start + limit
        email_subset = email_ids[start:end]

        email_list = []
        
        for eid in email_subset:
            _, msg_data = imap.fetch(eid, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])

                    # Extract subject and decode it properly
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or "utf-8")

                    # Extract sender
                    sender = msg["From"]

                    # Extract date
                    date = msg["Date"]

                    # Extract a small preview of the email body
                    body_preview = "No preview available"
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition"))

                            if content_type == "text/plain" and "attachment" not in content_disposition:
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                body_preview = body[:100]  # First 100 characters
                                break
                    else:
                        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                        body_preview = body[:100]

                    email_list.append({
                        "email_id": eid.decode(),
                        "subject": subject,
                        "from": sender,
                        "date": date,
                        "body_preview": body_preview
                    })

        imap.logout()
        return {"emails": email_list}

    except Exception as e:
        return {"error": f"Failed to fetch emails: {str(e)}"}