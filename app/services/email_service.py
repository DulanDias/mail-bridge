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
from app.services.jwt_service import decode_jwt
from app.models import MailboxConfig
from app.routes.ws import notify_clients
import json
import logging
from fastapi import HTTPException
import email.utils

# Configure logging
logging.basicConfig(level=logging.DEBUG)

def get_mailbox_config_from_token(token: str):
    """ Retrieve mailbox configuration from JWT token """
    try:
        email, password, imap_server, smtp_server, imap_port, smtp_port = decode_jwt(token)
        if not email or not imap_server or not smtp_server:
            raise Exception("Mailbox not found")
        return {
            "email": email,
            "password": password,
            "imap_server": imap_server,
            "smtp_server": smtp_server,
            "imap_port": imap_port,
            "smtp_port": smtp_port
        }
    except Exception as e:
        logging.error(f"Error retrieving mailbox config: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

@celery.task
def check_new_emails(mailbox_token: str):
    """ Background Task: Fetch New Emails """
    try:
        config = get_mailbox_config_from_token(mailbox_token)
        mailbox_email = config["email"]  # Extract mailbox_email from token
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])
        imap.select("INBOX")
        _, messages = imap.search(None, "UNSEEN")
        email_ids = messages[0].split()
        imap.logout()

        # Notify WebSocket clients
        new_emails = [{"email_id": eid.decode()} for eid in email_ids]
        asyncio.run(notify_clients(mailbox_email, new_emails))

        return {"unread_count": len(email_ids)}
    except Exception as e:
        return {"error": f"Failed to check new emails: {str(e)}"}

@celery.task
def send_email_task(mailbox_token: str, email_data: dict):
    """ Background Task: Send Email via SMTP with Multi-Part (HTML + Plain Text) """
    try:
        # Decode the token to get mailbox configuration
        config = get_mailbox_config_from_token(mailbox_token)
        mailbox_email = config["email"]  # Extract mailbox_email from token

        # Format sender email
        sender_email = mailbox_email
        sender_name = email_data.get("from_name", sender_email)
        formatted_sender = f"{sender_name} <{sender_email}>"

        # Parse recipient lists (ensure they are lists)
        to_recipients = email_data.get("to", [])
        if isinstance(to_recipients, str):
            to_recipients = json.loads(to_recipients)

        cc_recipients = email_data.get("cc", [])
        if isinstance(cc_recipients, str):
            cc_recipients = json.loads(cc_recipients)

        bcc_recipients = email_data.get("bcc", [])
        if isinstance(bcc_recipients, str):
            bcc_recipients = json.loads(bcc_recipients)

        all_recipients = to_recipients + cc_recipients + bcc_recipients  # Combine all for SMTP

        if not all_recipients:
            return {"error": "No recipients provided"}

        # Get email content type from request (default to HTML)
        content_type = email_data.get("content_type", "html").lower()
        email_body = email_data.get("body", "")

        # Create Email Message
        if content_type == "plain":
            # Plain text email (no multipart)
            msg = EmailMessage()
            msg.set_content(email_body)  # Only plain text
        else:
            # Multi-Part Email with Plain Text & HTML
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText("This email requires an HTML-supported email client to view properly.", "plain"))
            msg.attach(MIMEText(email_body, "html"))

        # Set email headers
        msg["Message-ID"] = email.utils.make_msgid()
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

        # Handle read receipt
        if email_data.get("read_receipt", False):
            read_receipt_email = email_data.get("read_receipt_email", sender_email)
            msg["Disposition-Notification-To"] = read_receipt_email

        # Send email via SMTP
        response = asyncio.run(aiosmtplib.send(
            msg.as_string(),  # Send as raw message
            sender=config["email"],  # Explicitly pass sender email
            recipients=all_recipients,  # Provide recipients explicitly
            hostname=config["smtp_server"], port=config["smtp_port"],
            username=config["email"], password=config["password"]
        ))

        # Save to Sent folder
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])
        sent_folder = get_imap_folder_name(imap, "Sent")

        imap.append(sent_folder, None, None,msg.as_bytes())
        imap.logout()

        return {"message": "Email sent successfully", "response": str(response)}

    except Exception as e:
        return {"error": f"Failed to send email: {str(e)}", "traceback": traceback.format_exc()}

def validate_mailbox(config: MailboxConfig):
    """ Validate IMAP/SMTP connection using mailbox configuration """
    try:
        logging.debug(f"Validating mailbox config: {config}")
        # Validate IMAP
        imap = imaplib.IMAP4_SSL(config.imap_server, config.imap_port)
        imap.login(config.email, config.password)
        imap.select("INBOX")
        imap.logout()
    except imaplib.IMAP4.error as e:
        logging.error(f"IMAP Validation Failed: {str(e)}")
        return False, f"IMAP Validation Failed: {str(e)}"
    except Exception as e:
        logging.error(f"IMAP Connection Error: {str(e)}")
        return False, f"IMAP Connection Error: {str(e)}"

    try:
        # Validate SMTP
        smtp = smtplib.SMTP(config.smtp_server, config.smtp_port)
        smtp.starttls()
        smtp.login(config.email, config.password)
        smtp.quit()
    except smtplib.SMTPAuthenticationError as e:
        logging.error(f"SMTP Authentication Failed: {str(e)}")
        return False, f"SMTP Authentication Failed: {str(e)}"
    except Exception as e:
        logging.error(f"SMTP Connection Error: {str(e)}")
        return False, f"SMTP Connection Error: {str(e)}"

    return True, None

def get_emails(config: dict, page: int = 1, limit: int = 20):
    """ Fetch emails from the mailbox using IMAP and return subject, sender, date, partial email body, 'to' list, and flags """
    try:
        # Connect to IMAP server
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])
        imap.select("INBOX", readonly=True)

        # Fetch all email IDs
        _, messages = imap.search(None, "ALL")
        email_ids = messages[0].split()

        # Paginate results
        start = (page - 1) * limit
        end = start + limit
        email_subset = email_ids[start:end]

        email_list = []
        
        for eid in email_subset:
            _, msg_data = imap.fetch(eid, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    # Extract header fields
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or "utf-8")
                    sender = msg["From"]
                    date = msg["Date"]
                    body_preview = "No preview available"
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition"))
                            if content_type == "text/plain" and "attachment" not in content_disposition:
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                body_preview = body[:100]
                                break
                    else:
                        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                        body_preview = body[:100]
                    # Extract the Message-ID header
                    message_id = msg.get("Message-ID") or "Unknown"
                    logging.info(f"Message-ID is true : {message_id}")
                    email_list.append({
                        "email_id": eid.decode(),
                        "message_id": message_id,  # Ensure Message-ID is returned
                        "subject": subject or "No Subject",
                        "from": sender or "Unknown Sender",
                        "date": date or "Unknown Date",
                        "body_preview": body_preview,
                        "to": [recipient.strip() for recipient in msg.get_all("To", [])],
                        "cc": [recipient.strip() for recipient in msg.get_all("Cc", [])] if msg.get_all("Cc") else [],
                        "flags": get_email_flags(config, eid.decode())
                    })

        imap.logout()
        return {"emails": email_list}

    except Exception as e:
        return {"error": f"Failed to fetch emails: {str(e)}", "traceback": traceback.format_exc()}

def get_full_email_from_inbox(mailbox_token: str, email_id: str):
    """ Fetch the full email including HTML body & attachments """

    # Retrieve stored mailbox configuration
    config = get_mailbox_config_from_token(mailbox_token)

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
        "trash": ["Trash", "[Gmail]/Trash", "Deleted Items", "Bin"],
        "sent": ["Sent", "[Gmail]/Sent Mail", "Sent Items"],
        "archive": ["Archive", "[Gmail]/All Mail"],
        "drafts": ["Drafts", "[Gmail]/Drafts"]
    }
    # Default to provided folder if no mapping is found
    desired_names = folder_mappings.get(folder_name.lower(), [folder_name])
    # List available folders
    _, folders = imap.list()
    folder_list = [f.decode().split(' "." ')[-1].strip() for f in folders]
    lower_folders = [f.lower() for f in folder_list]
    
    for desired in desired_names:
        if desired.lower() in lower_folders:
            # Return the actual folder name as returned by the server
            return folder_list[lower_folders.index(desired.lower())]
    
    return folder_name  # Fallback to the requested folder name


def get_emails_by_folder(mailbox_token: str, folder: str, page: int = 1, limit: int = 20):
    """ Fetch emails from a specific folder with pagination, including 'to' list, flags, and message_id """
    config = get_mailbox_config_from_token(mailbox_token)
    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])
        correct_folder = get_imap_folder_name(imap, folder)
        print(f"Selected IMAP Folder: {correct_folder}")
        status, messages = imap.select(correct_folder, readonly=True)
        if status != "OK":
            return {"error": f"Failed to select folder: {correct_folder}"}
        _, messages = imap.search(None, "ALL")
        email_ids = messages[0].split()
        start = max(0, len(email_ids) - (page * limit))
        end = start + limit
        email_subset = email_ids[start:end]
        email_list = []

        for eid in email_subset:
            _, msg_data = imap.fetch(eid, "(BODY.PEEK[])")
            logging.info(f"email data : {msg_data}")

            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or "utf-8")
                    sender = msg["From"]
                    date = msg["Date"]
                    if not date:
                        _, internal_data = imap.fetch(eid, "(INTERNALDATE)")
                        internal_response = internal_data[0].decode()
                        start_index = internal_response.find('"')
                        end_index = internal_response.find('"', start_index + 1)
                        if start_index != -1 and end_index != -1:
                            date = internal_response[start_index+1:end_index]
                    body_preview = "No preview available"
                    attachments = []
                    
                    # Process email parts to find body and attachments
                    if msg.is_multipart():
                        print("msg is multipart")
                        for part in msg.walk():
                            print(part.get_content_type())
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition"))
                            
                            # Check for attachments
                            if "attachment" in content_disposition:
                                filename = part.get_filename()
                                if filename:
                                    # Only include metadata (not content) to keep response size reasonable
                                    attachments.append({
                                        "filename": filename,
                                        "content_type": content_type,
                                        "size": len(part.get_payload(decode=True))
                                    })
                            # Extract body preview
                            elif content_type == "text/plain" and "attachment" not in content_disposition:
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                body_preview = body[:100]
                                break
                    else:
                        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                        body_preview = body[:100]

                    flags = get_email_flags(config, eid.decode())
                    
                    email_list.append({
                        "email_id": eid.decode(),
                        "message_id": msg.get("Message-ID") or "Unknown",
                        "subject": subject,
                        "from": sender,
                        "date": date,
                        "body_preview": body_preview,
                        "to": [recipient.strip() for recipient in msg.get_all("To", [])],
                        "flags": flags,
                        "isStarred": "is_star" in flags,
                        "isSeen": "is_seen" in flags,
                        "has_attachments": len(attachments) > 0,
                        "attachments": attachments
                    })

        imap.logout()
        return {"emails": email_list}

    except Exception as e:
        return {"error": f"Failed to fetch emails from {folder}: {str(e)}"}
    
def get_imap_folder_name(imap, folder_name):
    """ Get the correct IMAP folder name based on the email provider. """
    folder_mappings = {
        "trash": ["Trash", "[Gmail]/Trash", "Deleted Items", "Bin"],
        "sent": ["Sent", "[Gmail]/Sent Mail", "Sent Items"],
        "archive": ["Archive", "[Gmail]/All Mail"],
        "drafts": ["Drafts", "[Gmail]/Drafts"]
    }
    # Default to provided folder if no mapping is found
    desired_names = folder_mappings.get(folder_name.lower(), [folder_name])
    # List available folders
    _, folders = imap.list()
    folder_list = [f.decode().split(' "." ')[-1].strip() for f in folders]
    lower_folders = [f.lower() for f in folder_list]
    
    for desired in desired_names:
        if desired.lower() in lower_folders:
            # Return the actual folder name as returned by the server
            return folder_list[lower_folders.index(desired.lower())]
    
    return folder_name  # Fallback to the requested folder name


def get_emails_by_draft_folder(mailbox_token: str, folder: str, page: int = 1, limit: int = 20):
    """ Fetch emails from a specific folder with pagination, including 'to' list, flags, and message_id """
    config = get_mailbox_config_from_token(mailbox_token)
    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])
        correct_folder = get_imap_folder_name(imap, folder)
        print(f"Selected IMAP Folder: {correct_folder}")
        status, messages = imap.select(correct_folder, readonly=True)
        if status != "OK":
            return {"error": f"Failed to select folder: {correct_folder}"}
        _, messages = imap.search(None, "ALL")
        email_ids = messages[0].split()
        start = max(0, len(email_ids) - (page * limit))
        end = start + limit
        email_subset = email_ids[start:end]
        email_list = []

        for eid in email_subset:
            _, msg_data = imap.fetch(eid, "(BODY.PEEK[])")
            logging.info(f"email data : {msg_data}")

            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or "utf-8")
                    sender = msg["To"]
                    date = msg["Date"]
                    if not date:
                        _, internal_data = imap.fetch(eid, "(INTERNALDATE)")
                        internal_response = internal_data[0].decode()
                        start_index = internal_response.find('"')
                        end_index = internal_response.find('"', start_index + 1)
                        if start_index != -1 and end_index != -1:
                            date = internal_response[start_index+1:end_index]
                    body_preview = "No preview available"
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition"))
                            if content_type == "text/plain" and "attachment" not in content_disposition:
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                body_preview = body[:100]
                                break
                    else:
                        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                        body_preview = body[:100]

                    flags = get_email_flags(config, eid.decode())
                    
                    email_list.append({
                        "email_id": eid.decode(),
                        "message_id": msg.get("Message-ID") or "Unknown",
                        "subject": subject,
                        "from": [recipient.strip() for recipient in msg.get_all("To", [])],
                        "date": date,
                        "body_preview": body_preview,
                        "to": sender,
                        "flags": flags,
                        "isStarred": "is_star" in flags,
                        "isSeen": "is_seen" in flags
                    })

        imap.logout()
        return {"emails": email_list}

    except Exception as e:
        return {"error": f"Failed to fetch emails from {folder}: {str(e)}"}

def delete_email(mailbox_token: str, email_id: str):
    """ Move an email to the Trash folder first. If it's already in Trash, permanently delete it. """

    config = get_mailbox_config_from_token(mailbox_token)

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
                # If in Trash, append the \Deleted flag
                for eid in messages[0].split():
                    imap.store(eid, "+FLAGS", "\\Deleted")
                imap.expunge()
                imap.logout()
                return {"message": f"Email {email_id} permanently deleted from Trash"}

        # Otherwise, move to Trash
        imap.select("INBOX")
        imap.copy(email_id, trash_folder)
        for eid in messages[0].split():
            imap.store(eid, "+FLAGS", "\\Deleted")
        imap.expunge()
        imap.logout()
        return {"message": f"Email {email_id} moved to Trash"}

    except Exception as e:
        return {"error": f"Failed to delete email {email_id}: {str(e)}"}

def move_email(mailbox_token: str, email_id: str, from_folder: str, to_folder: str):
    """ Move an email between folders like Spam -> Inbox, Inbox -> Archive, etc. """

    config = get_mailbox_config_from_token(mailbox_token)

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

def empty_trash(mailbox_token: str):
    """ Permanently delete all emails in the Trash folder """

    config = get_mailbox_config_from_token(mailbox_token)

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
    
def delete_email_from_trash(mailbox_token: str, email_id: str):
    """ Permanently delete a specific email from the Trash folder """

    config = get_mailbox_config_from_token(mailbox_token)

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

        # Append the \Deleted flag
        for eid in email_ids:
            imap.store(eid, "+FLAGS", "\\Deleted")

        # Expunge (permanently delete)
        imap.expunge()
        imap.logout()

        return {"message": f"Email {email_id} permanently deleted from Trash"}

    except Exception as e:
        return {"error": f"Failed to delete email {email_id} from Trash: {str(e)}"}


def get_full_email_from_folder(config: str, email_id: str, folder: str):
    """ Fetch full email content including attachments, 'to' list, and flags """

    # config = get_mailbox_config_from_token(mailbox_token)

    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Get correct folder name
        folder_name = get_imap_folder_name(imap, folder)

        # Select folder
        status, messages = imap.select(folder_name)
        if status != "OK":
            return {"error": f"Failed to select folder: {folder_name}"}
        
        # # Fetch full email
        _, msg_data = imap.fetch(email_id, "(RFC822)")
        if not msg_data or msg_data[0] is None:
            imap.logout()
            return {"error": f"Failed to fetch full email: Email ID {email_id} may be invalid or missing"}

        msg = email.message_from_bytes(msg_data[0][1])
        logging.info(f"msg : {msg}")

        # Extract headers
        subject, encoding = decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding or "utf-8")

        to, encoding = decode_header(msg["To"])[0]
        if isinstance(to, bytes):
            subject = to.decode(encoding or "utf-8")

        sender = msg["From"]
        date = msg["Date"]

        # Add fallback for missing Date header
        if not date:
            _, internal_data = imap.fetch(email_id, "(INTERNALDATE)")
            internal_response = internal_data[0].decode()
            start_index = internal_response.find('"')
            end_index = internal_response.find('"', start_index + 1)
            if start_index != -1 and end_index != -1:
                date = internal_response[start_index+1:end_index]

        # Extract email body
        body = "No content available"
        attachments = []
        html_body = None
        plain_body = None

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if "attachment" not in content_disposition:
                    if content_type == "text/plain":
                        plain_body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    elif content_type == "text/html":
                        html_body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                elif "attachment" in content_disposition:
                    filename = part.get_filename()
                    file_data = part.get_payload(decode=True)
                    attachments.append({
                        "filename": filename,
                        "size": len(file_data)
                    })
            
            # Prioritize HTML content if available, otherwise use plain text
            if html_body:
                body = html_body
            elif plain_body:
                body = plain_body
        else:
            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

        imap.logout()

        return {
            "email_id": email_id,
            "subject": subject,
            "from": sender,
            "date": date,
            "body": body,
            "attachments": attachments,
            "to": to,
            "flags": get_email_flags(config, email_id)
        }

    except Exception as e:
        return {"error": f"Failed to fetch full email: {str(e)}"}

def mark_email_as_read(mailbox_token: str, email_id: str):
    """ Mark an email as read in the mailbox """

    config = get_mailbox_config_from_token(mailbox_token)

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

        # Append the "is_seen" label to mark as read
        for eid in email_ids:
            imap.store(eid, "+FLAGS", "is_seen")

        imap.logout()
        return {"message": f"Email {email_id} marked as read"}

    except Exception as e:
        return {"error": f"Failed to mark email {email_id} as read: {str(e)}"}
    
def mark_email_as_unread(mailbox_token: str, email_id: str):
    """ Mark an email as unread in the mailbox """

    config = get_mailbox_config_from_token(mailbox_token)

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

        # Remove the "is_seen" label to mark as unread
        for eid in email_ids:
            imap.store(eid, "-FLAGS", "is_seen")

        imap.logout()
        return {"message": f"Email {email_id} marked as unread"}

    except Exception as e:
        return {"error": f"Failed to mark email {email_id} as unread: {str(e)}"}
    
def save_draft(mailbox_token: str, draft_data: dict):
    """Save an email as a draft in the Drafts folder."""
    config = get_mailbox_config_from_token(mailbox_token)
    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        drafts_folder = get_imap_folder_name(imap, "Drafts")

        msg = EmailMessage()
        msg["From"] = f"{draft_data.get('sender_name', '')} <{config['email']}>"
        msg["To"] = ", ".join(draft_data.get("to", []))
        msg["CC"] = ", ".join(draft_data.get("cc", []))
        msg["BCC"] = ", ".join(draft_data.get("bcc", []))
        msg["Subject"] = draft_data.get("subject", "")
        msg.set_content(draft_data.get("body", ""))

        # Handle attachments
        for attachment in draft_data.get("attachments", []):
            file_data = base64.b64decode(attachment["content"])
            msg.add_attachment(file_data, filename=attachment["filename"])

        imap.append(drafts_folder, None, None, msg.as_bytes())
        imap.logout()
        return {"message": "Draft saved successfully"}
    except Exception as e:
        return {"error": f"Failed to save draft: {str(e)}"}

def get_draft(mailbox_token: str, email_id: str):
    """ Fetch a saved draft email """

    config = get_mailbox_config_from_token(mailbox_token)

    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Get the correct Drafts folder name
        drafts_folder = get_imap_folder_name(imap, "Drafts")

        # Select Drafts folder
        status, _ = imap.select(drafts_folder)
        if status != "OK":
            return {"error": f"Failed to select Drafts folder"}

        # Search for the draft by Message-ID
        # _, messages = imap.search(None, f'HEADER Message-ID "{email_id}"')
        # email_ids = messages[0].split()

        # if not email_ids:
        #     imap.logout()
        #     return {"error": f"Draft {email_id} not found"}

        # Fetch draft content
        _, msg_data = imap.fetch(email_id[0], "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])

        # Extract details
        subject, encoding = decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding or "utf-8")

        sender = msg["From"]
        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

        imap.logout()

        return {
            "email_id": email_id,
            "subject": subject,
            "from": sender,
            "body": body
        }

    except Exception as e:
        return {"error": f"Failed to fetch draft: {str(e)}"}

def reply_to_email(mailbox_token: str, email_id: str, email_data):
    """ Reply to an email """

    config = get_mailbox_config_from_token(mailbox_token)

    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Select INBOX to fetch original email
        imap.select("INBOX")
        _, messages = imap.search(None, f'HEADER Message-ID "{email_id}"')
        email_ids = messages[0].split()

        if not email_ids:
            imap.logout()
            return {"error": f"Original email {email_id} not found"}

        # Fetch original email
        _, msg_data = imap.fetch(email_ids[0], "(BODY.PEEK[])")
        msg = email.message_from_bytes(msg_data[0][1])

        # Create reply
        reply_msg = EmailMessage()
        reply_msg["From"] = msg["From"]
        reply_msg["To"] = f"{email_data.get('sender_name', '')} <{config['email']}>"
        reply_msg["Subject"] = f"Re: {msg['Subject']}"
        reply_msg.set_content(email_data.get("body", ""))

        # Send reply
        asyncio.run(aiosmtplib.send(reply_msg.as_string(), hostname=config["smtp_server"], port=587, username=config["email"], password=config["password"]))

        # Save reply in Sent folder
        sent_folder = get_imap_folder_name(imap, "Sent")
        imap.append(sent_folder, None, None, reply_msg.as_bytes())
        imap.logout()

        return {"message": "Reply sent successfully"}

    except Exception as e:
        return {"error": f"Failed to reply: {str(e)}"}

def forward_email(mailbox_token: str, email_id: str, email_data):
    """ Forward an email """

    config = get_mailbox_config_from_token(mailbox_token)

    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Select INBOX to fetch original email
        imap.select("INBOX")
        _, messages = imap.search(None, f'HEADER Message-ID "{email_id}"')
        email_ids = messages[0].split()

        if not email_ids:
            imap.logout()
            return {"error": f"Original email {email_id} not found"}

        # Fetch original email
        _, msg_data = imap.fetch(email_ids[0], "(BODY.PEEK[])")
        msg = email.message_from_bytes(msg_data[0][1])

        # Create forward message
        forward_msg = EmailMessage()
        forward_msg["From"] = f"{email_data.get('sender_name', '')} <{config['email']}>"
        forward_msg["To"] = ", ".join(email_data.get("to", []))
        forward_msg["Subject"] = f"Fwd: {msg['Subject']}"
        forward_msg.set_content(email_data.get("body", ""))

        # Attach original email
        forward_msg.add_attachment(msg.as_bytes(), maintype="message", subtype="rfc822")

        # Send forward
        asyncio.run(aiosmtplib.send(forward_msg.as_string(), hostname=config["smtp_server"], port=587, username=config["email"], password=config["password"]))

        # Save forward in Sent folder
        sent_folder = get_imap_folder_name(imap, "Sent")
        imap.append(sent_folder, None, None, forward_msg.as_bytes())
        imap.logout()

        return {"message": "Email forwarded successfully"}

    except Exception as e:
        return {"error": f"Failed to forward email: {str(e)}"}
    
def reply_all_email(mailbox_token: str, email_id: str):
    """ Reply to all recipients of an email """

    config = get_mailbox_config_from_token(mailbox_token)

    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Select INBOX to fetch original email
        imap.select("INBOX")
        _, messages = imap.search(None, f'HEADER Message-ID "{email_id}"')
        email_ids = messages[0].split()

        if not email_ids:
            imap.logout()
            return {"error": f"Original email {email_id} not found"}

        # Fetch original email
        _, msg_data = imap.fetch(email_ids[0], "(BODY.PEEK[])")
        msg = email.message_from_bytes(msg_data[0][1])

        # Create reply-all message
        reply_msg = EmailMessage()
        reply_msg["From"] = config["email"]
        reply_msg["To"] = msg["From"]
        reply_msg["Cc"] = msg["Cc"]
        reply_msg["Subject"] = f"Re: {msg['Subject']}"
        reply_msg.set_content("Replying to all recipients")

        # Send reply-all
        asyncio.run(aiosmtplib.send(reply_msg.as_string(), hostname=config["smtp_server"], port=587, username=config["email"], password=config["password"]))

        # Save reply in Sent folder
        sent_folder = get_imap_folder_name(imap, "Sent")
        imap.append(sent_folder, None, None, reply_msg.as_bytes())
        imap.logout()

        return {"message": "Reply-all sent successfully"}

    except Exception as e:
        return {"error": f"Failed to reply-all: {str(e)}"}
    
def update_draft(mailbox_token: str, email_id: str, draft_data: dict):
    """Update an existing draft email."""
    config = get_mailbox_config_from_token(mailbox_token)
    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        drafts_folder = get_imap_folder_name(imap, "Drafts")
        imap.select(drafts_folder)

        # Search for the draft by Message-ID
        _, messages = imap.search(None, f'HEADER Message-ID "{email_id}"')
        email_ids = messages[0].split()

        if not email_ids:
            imap.logout()
            return {"error": f"Draft {email_id} not found"}

        # Delete the existing draft
        for eid in email_ids:
            imap.store(eid, "+FLAGS", "\\Deleted")
        imap.expunge()

        # Create a new draft message
        msg = EmailMessage()
        msg["From"] = f"{draft_data.get('sender_name', '')} <{config['email']}>"
        msg["To"] = ", ".join(draft_data.get("to", []))
        msg["CC"] = ", ".join(draft_data.get("cc", []))
        msg["BCC"] = ", ".join(draft_data.get("bcc", []))
        msg["Subject"] = draft_data.get("subject", "")
        msg.set_content(draft_data.get("body", ""))

        # Handle attachments
        for attachment in draft_data.get("attachments", []):
            file_data = base64.b64decode(attachment["content"])
            msg.add_attachment(file_data, filename=attachment["filename"])

        imap.append(drafts_folder, None, None, msg.as_bytes())
        imap.logout()
        return {"message": "Draft updated successfully"}
    except Exception as e:
        return {"error": f"Failed to update draft: {str(e)}"}

def delete_draft(mailbox_token: str, email_id: str):
    """ Delete a draft email """

    config = get_mailbox_config_from_token(mailbox_token)

    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Get the correct Drafts folder name
        drafts_folder = get_imap_folder_name(imap, "Drafts")

        # Select Drafts folder
        status, _ = imap.select(drafts_folder)
        if status != "OK":
            return {"error": f"Failed to select Drafts folder"}

        # Search for the draft by Message-ID
        _, messages = imap.search(None, f'HEADER Message-ID "{email_id}"')
        email_ids = messages[0].split()

        if not email_ids:
            imap.logout()
            return {"error": f"Draft {email_id} not found"}

        # Mark draft for deletion
        for eid in email_ids:
            imap.store(eid, "+FLAGS", "\\Deleted")

        # Expunge (permanently delete)
        imap.expunge()
        imap.logout()

        return {"message": f"Draft {email_id} deleted successfully"}

    except Exception as e:
        return {"error": f"Failed to delete draft: {str(e)}"}
    
def get_unread_count(mailbox_token: str):
    """ Get the total number of unread emails in the mailbox (emails not marked with 'is_seen') """

    config = get_mailbox_config_from_token(mailbox_token)

    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])
        imap.select("INBOX")

        # Search for emails that do NOT have the custom "is_seen" flag
        _, messages = imap.search(None, 'NOT', 'is_seen')
        email_ids = messages[0].split()
        unread_count = len(email_ids)

        imap.logout()
        return {"unread_count": unread_count}

    except Exception as e:
        return {"error": f"Failed to get unread count: {str(e)}"}
    
def search_emails(mailbox_token: str, search_criteria: str):
        """ Search emails in the mailbox based on given criteria """

        config = get_mailbox_config_from_token(mailbox_token)

        try:
            imap = imaplib.IMAP4_SSL(config["imap_server"])
            imap.login(config["email"], config["password"])
            imap.select("INBOX")

            # Search emails based on criteria
            status, messages = imap.search(None, search_criteria)
            if status != "OK":
                return {"error": f"Failed to search emails with criteria: {search_criteria}"}

            email_ids = messages[0].split()
            email_list = []

            for eid in email_ids:
                _, msg_data = imap.fetch(eid, "(BODY.PEEK[])")
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
            return {"error": f"Failed to search emails: {str(e)}"}
        
def get_email_attachments(mailbox_token: str, email_id: str):
    """ Fetch attachments from a specific email """

    config = get_mailbox_config_from_token(mailbox_token)

    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Select INBOX
        imap.select("INBOX")

        # Search for the email by Message-ID
        _, messages = imap.search(None, f'HEADER Message-ID "{email_id}"')
        email_ids = messages[0].split()

        if not email_ids:
            imap.logout()
            return {"error": f"Email {email_id} not found"}

        # Fetch the email
        _, msg_data = imap.fetch(email_ids[0], "(BODY.PEEK[])")
        msg = email.message_from_bytes(msg_data[0][1])

        # Extract attachments
        attachments = []
        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition"))
            if "attachment" in content_disposition:
                filename = part.get_filename()
                file_data = part.get_payload(decode=True)
                attachments.append({
                    "filename": filename,
                    "size": len(file_data),
                    "content": base64.b64encode(file_data).decode("utf-8")
                })

        imap.logout()
        return {"attachments": attachments}

    except Exception as e:
        return {"error": f"Failed to fetch attachments: {str(e)}"}
    
def star_email(mailbox_token: str, email_id: str):
    """ Star an email in the mailbox """

    config = get_mailbox_config_from_token(mailbox_token)

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

        # Append the \Flagged flag
        for eid in email_ids:
            imap.store(eid, "+FLAGS", "\\Flagged")

        imap.logout()
        return {"message": f"Email {email_id} starred"}

    except Exception as e:
        return {"error": f"Failed to star email {email_id}: {str(e)}"}

def unstar_email(mailbox_token: str, email_id: str):
    """ Unstar an email in the mailbox """

    config = get_mailbox_config_from_token(mailbox_token)

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

        # Remove the \Flagged flag
        for eid in email_ids:
            imap.store(eid, "-FLAGS", "\\Flagged")

        imap.logout()
        return {"message": f"Email {email_id} unstarred"}

    except Exception as e:
        return {"error": f"Failed to unstar email {email_id}: {str(e)}"}

        
def get_email_attachment(mailbox_token: str, email_id: str, attachment_id: str):
    """ Fetch a specific attachment from an email by attachment ID """

    config = get_mailbox_config_from_token(mailbox_token)

    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Select INBOX
        imap.select("INBOX")

        # Search for the email by Message-ID
        _, messages = imap.search(None, f'HEADER Message-ID "{email_id}"')
        email_ids = messages[0].split()

        if not email_ids:
            imap.logout()
            return {"error": f"Email {email_id} not found"}

        # Fetch the email
        _, msg_data = imap.fetch(email_ids[0], "(BODY.PEEK[])")
        msg = email.message_from_bytes(msg_data[0][1])

        # Extract the specific attachment
        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition"))
            if "attachment" in content_disposition:
                filename = part.get_filename()
                if filename == attachment_id:
                    file_data = part.get_payload(decode=True)
                    imap.logout()
                    return {
                        "filename": filename,
                        "size": len(file_data),
                        "content": base64.b64encode(file_data).decode("utf-8")
                    }

        imap.logout()
        return {"error": f"Attachment {attachment_id} not found in email {email_id}"}

    except Exception as e:
        return {"error": f"Failed to fetch attachment: {str(e)}"}
            
def download_email_attachment(mailbox_token: str, email_id: str, attachment_id: str):
    """ Download a specific attachment from an email by attachment ID """

    config = get_mailbox_config_from_token(mailbox_token)

    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Select INBOX
        imap.select("INBOX")

        # Search for the email by Message-ID
        _, messages = imap.search(None, f'HEADER Message-ID "{email_id}"')
        email_ids = messages[0].split()

        if not email_ids:
            imap.logout()
            return {"error": f"Email {email_id} not found"}

        # Fetch the email
        _, msg_data = imap.fetch(email_ids[0], "(BODY.PEEK[])")
        msg = email.message_from_bytes(msg_data[0][1])

        # Extract the specific attachment
        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition"))
            if "attachment" in content_disposition:
                filename = part.get_filename()
                if filename == attachment_id:
                    file_data = part.get_payload(decode=True)
                    imap.logout()
                    return {
                        "filename": filename,
                        "size": len(file_data),
                        "content": base64.b64encode(file_data).decode("utf-8")
                    }

        imap.logout()
        return {"error": f"Attachment {attachment_id} not found in email {email_id}"}

    except Exception as e:
        return {"error": f"Failed to fetch attachment: {str(e)}"}
    
def filter_emails(mailbox_token: str, filter_type: str, page: int = 1, limit: int = 20):
    """ Filter emails in the mailbox based on the filter type """

    config = get_mailbox_config_from_token(mailbox_token)

    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])
        imap.select("INBOX")

        # Define search criteria based on filter type using custom "is_seen" flag
        if filter_type == "read":
            search_criteria = "is_seen"
        elif filter_type == "unread":
            search_criteria = "NOT is_seen"
        elif filter_type == "starred":
            search_criteria = "FLAGGED"
        elif filter_type == "unstarred":
            search_criteria = "UNFLAGGED"
        elif filter_type == "with_attachments":
            search_criteria = "HASATTACHMENT"
        else:
            return {"error": f"Invalid filter type: {filter_type}"}

        # Search emails based on the updated criteria
        status, messages = imap.search(None, search_criteria)
        if status != "OK":
            return {"error": f"Failed to filter emails with criteria: {search_criteria}"}

        email_ids = messages[0].split()

        # Paginate results
        start = max(0, len(email_ids) - (page * limit))
        end = start + limit
        email_subset = email_ids[start:end]

        email_list = []

        for eid in email_subset:
            _, msg_data = imap.fetch(eid, "(BODY.PEEK[])")
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
        return {"error": f"Failed to filter emails: {str(e)}"}

import re

def get_email_flags(config, email_id: str, folder: str = "INBOX"):
    """Fetch flags for the given email_id using IMAP fetch."""
    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])
        imap.select(folder)
        # Fetch flags using the whole email_id (not email_id[0])
        _, msg_data = imap.fetch(email_id, "(FLAGS)")
        flags_response = msg_data[0].decode()
        # Use regex to extract content inside the inner parenthesis after 'FLAGS'
        m = re.search(r'FLAGS\s+\((.*?)\)', flags_response)
        flags = m.group(1) if m else ""
        imap.logout()
        # Return a list of non-empty flag tokens
        return [flag for flag in flags.split() if flag]
    except Exception as e:
        return []
    
def get_starred_emails(mailbox_token: str, page: int = 1, limit: int = 20):
    config = get_mailbox_config_from_token(mailbox_token)
    folder = "INBOX"
    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])
        correct_folder = get_imap_folder_name(imap, folder)
        print(f"Selected IMAP Folder: {correct_folder}")
        status, messages = imap.select(correct_folder, readonly=True)
        if status != "OK":
            return {"error": f"Failed to select folder: {correct_folder}"}
        _, messages = imap.search(None, "ALL")
        email_ids = messages[0].split()
        start = max(0, len(email_ids) - (page * limit))
        end = start + limit
        email_subset = email_ids[start:end]
        email_list = []

        for eid in email_subset:
            _, msg_data = imap.fetch(eid, "(BODY.PEEK[])")
            logging.info(f"email data : {msg_data}")

            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding or "utf-8")
                    sender = msg["From"]
                    date = msg["Date"]
                    if not date:
                        _, internal_data = imap.fetch(eid, "(INTERNALDATE)")
                        internal_response = internal_data[0].decode()
                        start_index = internal_response.find('"')
                        end_index = internal_response.find('"', start_index + 1)
                        if start_index != -1 and end_index != -1:
                            date = internal_response[start_index+1:end_index]
                    body_preview = "No preview available"
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            content_disposition = str(part.get("Content-Disposition"))
                            if content_type == "text/plain" and "attachment" not in content_disposition:
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                body_preview = body[:100]
                                break
                    else:
                        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                        body_preview = body[:100]

                    flags = get_email_flags(config, eid.decode())

                    # Check if the email is starred
                    if "is_star" in flags:
                        email_list.append({
                            "email_id": eid.decode(),
                            "message_id": msg.get("Message-ID") or "Unknown",
                            "subject": subject,
                            "from": sender,
                            "date": date,
                            "body_preview": body_preview,
                            "to": [recipient.strip() for recipient in msg.get_all("To", [])],
                            "flags": flags,
                            "isStarred": "is_star" in flags,
                            "isSeen": "is_seen" in flags
                        })

        imap.logout()
        return {"emails": email_list}

    except Exception as e:
        return {"error": f"Failed to fetch emails from {folder}: {str(e)}"}
    








def get_email_recipients(config, email_id: str, recipient_type: str, folder: str = "INBOX"):
    """ Fetch recipients using the sequence number (email_id) directly """
    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])
        imap.select(folder)
        _, msg_data = imap.fetch(email_id, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])
        recipients = msg.get_all(recipient_type, [])
        imap.logout()
        return [recipient.strip() for recipient in recipients] if recipients else []
    except Exception as e:
        return []
    
    
def get_email_count(mailbox_token: str, folder: str):
    """ Get the total number of emails in a specified folder """

    config = get_mailbox_config_from_token(mailbox_token)

    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Get the correct folder name
        folder_name = get_imap_folder_name(imap, folder)

        # Select the folder
        status, messages = imap.select(folder_name)
        if status != "OK":
            return {"error": f"Failed to select folder: {folder_name}"}

        # Count the total number of emails
        _, messages = imap.search(None, "ALL")
        email_ids = messages[0].split()
        total_count = len(email_ids)

        imap.logout()
        return {"folder": folder, "total_count": total_count}

    except Exception as e:
        return {"error": f"Failed to get email count for folder {folder}: {str(e)}"}
    

def set_email_flag(mailbox_token: str, email_id: str, folder: str, flag: str, add: bool):
    """Set or remove a flag for an email in the specified folder.
    
    Searches by Message-ID in the given folder and applies the flag
    to all matching emails using their IMAP sequence numbers.
    """
    config = get_mailbox_config_from_token(mailbox_token)
    imap = None
    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Select the specified folder
        status, _ = imap.select(folder)
        if status != "OK":
            return {"error": f"Failed to select folder: {folder}"}

        # Search for email(s) by Message-ID header using IMAP's search command
        _, search_data = imap.search(None, f'HEADER Message-ID "{email_id}"')
        email_ids = search_data[0].split()

        if not email_ids:
            return {"error": f"Email {email_id} not found in {folder}"}

        # Optionally fetch and log header content of the first match
        fetch_status, header_data = imap.fetch(email_ids[0], '(BODY[HEADER])')
        if fetch_status == "OK" and header_data and isinstance(header_data[0], tuple):
            header_content = header_data[0][1].decode("utf-8", errors="ignore")
            logging.info(f"Header content for email {email_id}: {header_content}")
        else:
            logging.info(f"Failed to fetch header for email {email_id}")

        # For each matching email, set or remove the flag
        if add:
            for eid in email_ids:
                imap.store(eid, "+FLAGS", "is_star")
        else:
            for eid in email_ids:
                imap.store(eid, "-FLAGS", "is_star")

        action = "added" if add else "removed"
        return {"message": f"Flag {flag} {action} for email {email_id} in {folder}"}

    except Exception as e:
        return {"error": f"Failed to {('add' if add else 'remove')} flag {flag} for email {email_id}: {str(e)}"}
    finally:
        if imap:
            try:
                imap.logout()
            except Exception:
                pass

def set_email_flag_seen(mailbox_token: str, email_id: str, folder: str, flag: str, add: bool):
    """Set or remove a flag for an email in the specified folder.
    
    Searches by Message-ID in the given folder and applies the flag
    to all matching emails using their IMAP sequence numbers.
    """
    config = get_mailbox_config_from_token(mailbox_token)
    imap = None
    try:
        imap = imaplib.IMAP4_SSL(config["imap_server"])
        imap.login(config["email"], config["password"])

        # Select the specified folder
        status, _ = imap.select(folder)
        if status != "OK":
            return {"error": f"Failed to select folder: {folder}"}

        # Search for email(s) by Message-ID header using IMAP's search command
        _, search_data = imap.search(None, f'HEADER Message-ID "{email_id}"')
        email_ids = search_data[0].split()

        if not email_ids:
            return {"error": f"Email {email_id} not found in {folder}"}

        # Optionally fetch and log header content of the first match
        fetch_status, header_data = imap.fetch(email_ids[0], '(BODY[HEADER])')
        if fetch_status == "OK" and header_data and isinstance(header_data[0], tuple):
            header_content = header_data[0][1].decode("utf-8", errors="ignore")
            logging.info(f"Header content for email {email_id}: {header_content}")
        else:
            logging.info(f"Failed to fetch header for email {email_id}")

        # For each matching email, set or remove the flag
        if add:
            for eid in email_ids:
                imap.store(eid, "+FLAGS", "is_seen")
        else:
            for eid in email_ids:
                imap.store(eid, "-FLAGS", "is_seen")

        action = "added" if add else "removed"
        return {"message": f"Flag {flag} {action} for email {email_id} in {folder}"}

    except Exception as e:
        return {"error": f"Failed to {('add' if add else 'remove')} flag {flag} for email {email_id}: {str(e)}"}
    finally:
        if imap:
            try:
                imap.logout()
            except Exception:
                pass