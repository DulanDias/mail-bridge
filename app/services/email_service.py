import email
import smtplib
import imaplib
import aiosmtplib
import traceback
import asyncio
import base64
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import decode_header
from app.services.celery_worker import celery
from app.services.redis_service import get_mailbox_config
from app.models import MailboxConfig

@celery.task
def check_new_emails(mailbox_email: str):
    """ Background Task: Fetch New Emails """
    try:
        config = get_mailbox_config(mailbox_email)
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])
        imap.select("INBOX")
        _, messages = imap.search(None, "UNSEEN")
        email_ids = messages[0].split()
        imap.logout()
        return {"unread_count": len(email_ids)}
    except Exception as e:
        return {"error": f"Failed to check new emails: {str(e)}"}

@celery.task
def send_email_task(mailbox_email: str, email_data: dict):
    """ Background Task: Send Email via SMTP with Multi-Part (HTML + Plain Text) """
    try:
        config = get_mailbox_config(mailbox_email)

        # Format sender email
        sender_email = config["email"]
        sender_name = email_data.get("from_name", sender_email)
        formatted_sender = f"{sender_name} <{sender_email}>"

        # Get recipient lists
        to_recipients = email_data.get("to", [])
        cc_recipients = email_data.get("cc", [])
        bcc_recipients = email_data.get("bcc", [])
        all_recipients = to_recipients + cc_recipients + bcc_recipients  # Combine all for SMTP

        if not all_recipients:
            return {"error": "No recipients provided"}

        # Get email content type from request (default to HTML)
        content_type = email_data.get("content_type", "html").lower()
        email_body = email_data.get("body", "")

        # Create Email Message
        if content_type == "plain":
            # ✅ Plain text email (no multipart)
            msg = EmailMessage()
            msg.set_content(email_body)  # Only plain text
        else:
            # ✅ Multi-Part Email with Plain Text & HTML
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText("This email requires an HTML-supported email client to view properly.", "plain"))
            msg.attach(MIMEText(email_body, "html"))

        # Set email headers
        msg["From"] = formatted_sender
        msg["To"] = ", ".join(to_recipients)
        msg["CC"] = ", ".join(cc_recipients)
        msg["BCC"] = ", ".join(bcc_recipients)
        msg["Subject"] = email_data.get("subject", "No Subject")
        msg["Reply-To"] = formatted_sender

        # Process attachments (Decode from base64)
        attachments = email_data.get("attachments", [])
        for attachment in attachments:
            try:
                file_data = base64.b64decode(attachment["content"])
                attachment_part = MIMEText(file_data, "base64", "utf-8")
                attachment_part.add_header("Content-Disposition", f'attachment; filename="{attachment["filename"]}"')
                msg.attach(attachment_part)
            except Exception as e:
                return {"error": f"Failed to process attachment {attachment['filename']}: {str(e)}"}

        # ✅ Pass both `sender` and `recipients` explicitly in `aiosmtplib.send()`
        response = asyncio.run(aiosmtplib.send(
            msg.as_string(),  # Send as raw message
            sender=sender_email,  # ✅ Explicitly pass sender email
            recipients=all_recipients,  # ✅ Provide recipients explicitly
            hostname=config["smtp_server"], port=587,
            username=config["email"], password=config["password"]
        ))

        return {"message": "Email sent successfully", "response": str(response)}

    except Exception as e:
        return {"error": f"Failed to send email: {str(e)}", "traceback": traceback.format_exc()}

def validate_mailbox(config: MailboxConfig):
    """ Validate IMAP/SMTP connection """
    try:
        # Validate IMAP (incoming mail)
        imap = imaplib.IMAP4_SSL(config.imap_server)
        imap.login(config.email, config.password)
        imap.select("INBOX")
        imap.logout()

        # Validate SMTP (outgoing mail)
        smtp = smtplib.SMTP(config.smtp_server, 587)
        smtp.starttls()
        smtp.login(config.email, config.password)
        smtp.quit()

        return True, None
    except Exception as e:
        return False, f"Validation Failed: {str(e)}"

def get_emails(mailbox_email: str, page: int = 1, limit: int = 20):
    """ Fetch emails from the mailbox using IMAP and return subject, sender, date, and partial email body """

    try:
        # Retrieve stored mailbox configuration
        config = get_mailbox_config(mailbox_email)

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
                        "subject": subject or "No Subject",
                        "from": sender or "Unknown Sender",
                        "date": date or "Unknown Date",
                        "body_preview": body_preview
                    })

        imap.logout()
        return {"emails": email_list}

    except Exception as e:
        return {"error": f"Failed to fetch emails: {str(e)}", "traceback": traceback.format_exc()}
