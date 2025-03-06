import email
from email import policy
from email.parser import BytesParser
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

def get_full_email_from_inbox(mailbox_email: str, email_id: str):
    """ Fetch the full email including HTML body & attachments """

    # Retrieve stored mailbox configuration
    config = get_mailbox_config(mailbox_email)

    try:
        # Connect to IMAP server
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])
        imap.select("INBOX")

        # Fetch the email
        _, msg_data = imap.fetch(email_id, "(RFC822)")
        raw_email = msg_data[0][1]

        # Parse email
        msg = BytesParser(policy=policy.default).parsebytes(raw_email)

        # Extract email details
        subject = msg["Subject"]
        sender = msg["From"]
        date = msg["Date"]
        body = ""
        attachments = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if "attachment" in content_disposition:
                    # Handle attachments
                    attachment_data = part.get_payload(decode=True)
                    attachments.append({
                        "filename": part.get_filename(),
                        "content_type": content_type,
                        "base64_content": base64.b64encode(attachment_data).decode("utf-8")
                    })
                elif content_type == "text/plain":
                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                elif content_type == "text/html":
                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")

        else:
            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

        imap.logout()
        return {
            "email_id": email_id,
            "subject": subject,
            "from": sender,
            "date": date,
            "body": body,
            "attachments": attachments
        }

    except Exception as e:
        return {"error": f"Failed to fetch full email: {str(e)}"}
    
def get_imap_folder_name(imap, folder_name):
    """ Get the correct IMAP folder name based on the email provider. """
    folder_mappings = {
        "Trash": ["Trash", "[Gmail]/Trash", "Deleted Items", "Bin"],
        "Sent": ["Sent", "[Gmail]/Sent Mail", "Sent Items"],
        "Archive": ["Archive", "[Gmail]/All Mail"]
    }

    try:
        # List available folders
        _, folders = imap.list()
        folder_list = [f.decode().split(' "." ')[-1].strip() for f in folders]

        for mapped_name in folder_mappings.get(folder_name, [folder_name]):
            if mapped_name in folder_list:
                return mapped_name  # Return the correct folder name

        return folder_name  # Fallback to requested folder

    except Exception:
        return folder_name  # Fallback to requested folder


def get_emails_by_folder(mailbox_email: str, folder: str, page: int = 1, limit: int = 20):
    """ Fetch emails from Sent, Trash, or Archive folders with pagination """

    # Retrieve stored mailbox configuration
    config = get_mailbox_config(mailbox_email)

    try:
        # Connect to IMAP server
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Get the correct folder name
        correct_folder = get_imap_folder_name(imap, folder)

        # DEBUG: Print available folders
        print(f"Selected IMAP Folder: {correct_folder}")

        # Select the folder
        status, messages = imap.select(correct_folder, readonly=True)
        if status != "OK":
            return {"error": f"Failed to select folder: {correct_folder}"}

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

                    # Extract subject and decode properly
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
        return {"error": f"Failed to fetch emails from {folder}: {str(e)}"}


def delete_email(mailbox_email: str, email_id: str):
    """ Move an email to the Trash folder first. If it's already in Trash, permanently delete it. """

    config = get_mailbox_config(mailbox_email)

    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Get the Trash folder name
        trash_folder = get_imap_folder_name(imap, "Trash")

        # Check if the email is already in Trash
        status, _ = imap.select(trash_folder)
        if status == "OK":
            _, messages = imap.search(None, f'HEADER Message-ID "{email_id}"')
            if messages[0]:
                # If in Trash, permanently delete
                imap.store(email_id, "+FLAGS", "\\Deleted")
                imap.expunge()
                imap.logout()
                return {"message": f"Email {email_id} permanently deleted from Trash"}

        # Otherwise, move to Trash
        imap.select("INBOX")
        imap.copy(email_id, trash_folder)
        imap.store(email_id, "+FLAGS", "\\Deleted")
        imap.expunge()
        imap.logout()
        return {"message": f"Email {email_id} moved to Trash"}

    except Exception as e:
        return {"error": f"Failed to delete email {email_id}: {str(e)}"}

def move_email(mailbox_email: str, email_id: str, from_folder: str, to_folder: str):
    """ Move an email between folders like Spam -> Inbox, Inbox -> Archive, etc. """

    config = get_mailbox_config(mailbox_email)

    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Get correct IMAP folder names
        from_folder = get_imap_folder_name(imap, from_folder)
        to_folder = get_imap_folder_name(imap, to_folder)

        # Select the source folder
        status, _ = imap.select(from_folder)
        if status != "OK":
            return {"error": f"Failed to select source folder: {from_folder}"}

        # Search for email ID
        _, messages = imap.search(None, f'HEADER Message-ID "{email_id}"')
        email_ids = messages[0].split()

        if not email_ids:
            return {"error": f"Email {email_id} not found in {from_folder}"}

        # Move email
        imap.copy(email_id, to_folder)
        imap.store(email_id, "+FLAGS", "\\Deleted")  # Mark as deleted in old folder
        imap.expunge()

        imap.logout()
        return {"message": f"Email {email_id} moved from {from_folder} to {to_folder}"}

    except Exception as e:
        return {"error": f"Failed to move email {email_id}: {str(e)}"}

def empty_trash(mailbox_email: str):
    """ Permanently delete all emails in the Trash folder """

    config = get_mailbox_config(mailbox_email)

    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Get the correct Trash folder name
        trash_folder = get_imap_folder_name(imap, "Trash")

        # Select the Trash folder
        status, messages = imap.select(trash_folder)
        if status != "OK":
            return {"error": f"Failed to select Trash folder: {trash_folder}"}

        # Fetch all email IDs in Trash
        _, messages = imap.search(None, "ALL")
        email_ids = messages[0].split()

        if not email_ids:
            imap.logout()
            return {"message": "Trash is already empty"}

        # Mark all emails for deletion
        for eid in email_ids:
            imap.store(eid, "+FLAGS", "\\Deleted")

        # Expunge (permanently delete)
        imap.expunge()
        imap.logout()

        return {"message": "Trash emptied successfully. All emails permanently deleted."}

    except Exception as e:
        return {"error": f"Failed to empty Trash: {str(e)}"}
    
def delete_email_from_trash(mailbox_email: str, email_id: str):
    """ Permanently delete a specific email from the Trash folder """

    config = get_mailbox_config(mailbox_email)

    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Get the correct Trash folder name
        trash_folder = get_imap_folder_name(imap, "Trash")

        # Select the Trash folder
        status, messages = imap.select(trash_folder)
        if status != "OK":
            return {"error": f"Failed to select Trash folder: {trash_folder}"}

        # Search for the email by Message-ID
        _, messages = imap.search(None, f'HEADER Message-ID "{email_id}"')
        email_ids = messages[0].split()

        if not email_ids:
            imap.logout()
            return {"error": f"Email {email_id} not found in Trash"}

        # Mark email for deletion
        for eid in email_ids:
            imap.store(eid, "+FLAGS", "\\Deleted")

        # Expunge (permanently delete)
        imap.expunge()
        imap.logout()

        return {"message": f"Email {email_id} permanently deleted from Trash"}

    except Exception as e:
        return {"error": f"Failed to delete email {email_id} from Trash: {str(e)}"}


def get_full_email_from_folder(mailbox_email: str, email_id: str, folder: str):
    """ Fetch full email content including attachments from any folder """

    config = get_mailbox_config(mailbox_email)

    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Get correct folder name
        folder_name = get_imap_folder_name(imap, folder)

        # Select folder
        status, messages = imap.select(folder_name)
        if status != "OK":
            return {"error": f"Failed to select folder: {folder_name}"}

        # Search for the email by Message-ID
        _, messages = imap.search(None, f'HEADER Message-ID "{email_id}"')
        email_ids = messages[0].split()

        if not email_ids:
            imap.logout()
            return {"error": f"Email {email_id} not found in {folder}"}

        # Fetch full email
        _, msg_data = imap.fetch(email_ids[0], "(RFC822)")
        if not msg_data or msg_data[0] is None:
            imap.logout()
            return {"error": f"Failed to fetch full email: Email ID {email_id} may be invalid or missing"}

        msg = email.message_from_bytes(msg_data[0][1])

        # Extract headers
        subject, encoding = decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding or "utf-8")

        sender = msg["From"]
        date = msg["Date"]

        # Extract email body
        body = "No content available"
        attachments = []
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if content_type == "text/plain" and "attachment" not in content_disposition:
                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")

                elif "attachment" in content_disposition:
                    filename = part.get_filename()
                    file_data = part.get_payload(decode=True)
                    attachments.append({
                        "filename": filename,
                        "size": len(file_data)
                    })
        else:
            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

        imap.logout()

        return {
            "email_id": email_id,
            "subject": subject,
            "from": sender,
            "date": date,
            "body": body,
            "attachments": attachments
        }

    except Exception as e:
        return {"error": f"Failed to fetch full email: {str(e)}"}

def mark_email_as_read(mailbox_email: str, email_id: str):
    """ Mark an email as read in the mailbox """

    config = get_mailbox_config(mailbox_email)

    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Select the INBOX
        imap.select("INBOX")

        # Search for the email by Message-ID
        _, messages = imap.search(None, f'HEADER Message-ID "{email_id}"')
        email_ids = messages[0].split()

        if not email_ids:
            imap.logout()
            return {"error": f"Email {email_id} not found in INBOX"}

        # Mark email as read
        for eid in email_ids:
            imap.store(eid, "+FLAGS", "\\Seen")

        imap.logout()
        return {"message": f"Email {email_id} marked as read"}

    except Exception as e:
        return {"error": f"Failed to mark email {email_id} as read: {str(e)}"}
    
def mark_email_as_unread(mailbox_email: str, email_id: str):
    """ Mark an email as unread in the mailbox """

    config = get_mailbox_config(mailbox_email)

    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Select the INBOX
        imap.select("INBOX")

        # Search for the email by Message-ID
        _, messages = imap.search(None, f'HEADER Message-ID "{email_id}"')
        email_ids = messages[0].split()

        if not email_ids:
            imap.logout()
            return {"error": f"Email {email_id} not found in INBOX"}

        # Mark email as unread
        for eid in email_ids:
            imap.store(eid, "-FLAGS", "\\Seen")

        imap.logout()
        return {"message": f"Email {email_id} marked as unread"}

    except Exception as e:
        return {"error": f"Failed to mark email {email_id} as unread: {str(e)}"}