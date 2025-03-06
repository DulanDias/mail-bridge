# **📧 MailBridge - FastAPI Mailbox Backend**
🚀 **MailBridge** is a powerful, scalable, and feature-rich **email management backend** built with **FastAPI**, **Redis**, **Celery**, and **WebSockets**. It allows seamless management of multiple mailboxes, real-time email notifications, and background email processing.

---

## **📖 Features**
### **Multiple Mailboxes Support**
- Manage multiple email accounts dynamically.
- Store mailbox configurations securely in Redis.

### **IMAP & SMTP Integration**
- Fetch, send, delete, and archive emails.
- Supports both plain text and HTML email bodies.
- Handle attachments and inline images.

### **Real-time Email Updates**
- Uses **WebSockets** for live email notifications.
- Get notified instantly when new emails arrive.

### **Background Email Polling**
- Uses **Celery** for periodic email updates.
- Background tasks for sending and checking emails.

### **Unread Email Counters**
- Cached unread email counts per mailbox.
- Efficiently fetch unread email counts.

### **Email Metadata Handling**
- Extract sender name, subject, recipients, CC, and BCC.
- Decode email headers and handle different encodings.

### **Read Receipts Support**
- Track read receipts if supported by IMAP.
- Option to request read receipts when sending emails.

### **Rich Text & Inline Attachments**
- Supports HTML email bodies and inline images.
- Handle multipart emails with both plain text and HTML parts.

### **WebSocket over HTTP & HTTPS**
- Supports **WS and WSS** with reverse proxy integration.
- Secure WebSocket connections for real-time updates.

### **Comprehensive Swagger API Docs**
- Auto-generated API documentation.
- Detailed descriptions and examples for each endpoint.

### **Docker & Docker Compose Support**
- Easily deployable with Redis and Celery.
- Docker and Docker Compose configurations included.

---

## **🛠️ Tech Stack**
- **Backend:** FastAPI (Python 3.10+)
- **Database:** Redis (Caching & Background Tasks)
- **Email Handling:** IMAP & SMTP (`imaplib`, `aiosmtplib`)
- **Real-time Updates:** WebSockets (`fastapi.websockets`)
- **Background Tasks:** Celery (with Redis as broker)
- **Deployment:** Docker, Docker Compose
- **Security:** Rate Limiting (`slowapi`), Input Validation (`Pydantic`)

---

## **🚀 Getting Started**
### **1️⃣ Clone the Repository**
```
git clone https://github.com/DulanDias/mail-bridge.git
cd mail-bridge
```

### **2️⃣ Install Dependencies**
```
pip install -r requirements.txt
```

### **3️⃣ Start Redis Server**
```
redis-server
```

### **4️⃣ Start Celery Worker**
```
celery -A app.services.email_service worker --loglevel=info
```

### **5️⃣ Run FastAPI Server**
```
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## **🔌 WebSocket for Real-time Email Notifications**
### **1️⃣ Connect via WebSocket**
```
import websockets
import asyncio

async def listen_for_emails():
    async with websockets.connect("ws://localhost:8000/ws") as ws:
        await ws.send('{"emails": ["user1@example.com", "user2@example.com"]}')
        while True:
            message = await ws.recv()
            print(f"📩 New Email: {message}")

asyncio.run(listen_for_emails())
```
✅ **Live email updates without polling!**

---

## **🐳 Docker Deployment**
### **1️⃣ Build Docker Image**
```
docker build -t mailbridge .
```

### **2️⃣ Run Container**
```
docker run -d -p 8000:8000 mailbridge
```

### **3️⃣ Start Everything with Docker Compose**
```
docker-compose up -d
```

---

## **📜 API Endpoints**
### **Mailbox Configuration**
| **Endpoint** | **Method** | **Description** |
|-------------|-----------|----------------|
| `/config` | `POST` | Configure a mailbox (IMAP/SMTP) |

### **Email Sending**
| **Endpoint** | **Method** | **Description** |
|-------------|-----------|----------------|
| `/send` | `POST` | Send an email (with attachments) |

### **Email Fetching**
| **Endpoint** | **Method** | **Description** |
|-------------|-----------|----------------|
| `/emails` | `GET` | Fetch paginated email list |
| `/full-email/{email_id}` | `GET` | Fetch full email (with attachments) |
| `/emails/{folder}/full-email/{email_id}` | `GET` | Fetch full email from any folder |

### **Email Management**
| **Endpoint** | **Method** | **Description** |
|-------------|-----------|----------------|
| `/delete` | `POST` | Delete an email (move to trash) |
| `/emails/trash/delete/{email_id}` | `DELETE` | Permanently delete a specific email from Trash |
| `/emails/move` | `POST` | Move an email to a specified folder |
| `/emails/trash/empty` | `POST` | Permanently delete all emails in Trash |
| `/mark-read` | `POST` | Mark an email as read |
| `/mark-unread` | `POST` | Mark an email as unread |
| `/emails/star/{email_id}` | `POST` | Star an email |
| `/emails/unstar/{email_id}` | `POST` | Unstar an email |

### **Email Folders**
| **Endpoint** | **Method** | **Description** |
|-------------|-----------|----------------|
| `/emails/inbox` | `GET` | Fetch emails from Inbox |
| `/emails/trash` | `GET` | Fetch emails from Trash |
| `/emails/spam` | `GET` | Fetch emails from Spam |
| `/emails/drafts` | `GET` | Fetch emails from Drafts |
| `/emails/sent` | `GET` | Fetch emails from Sent |
| `/emails/archive` | `GET` | Fetch emails from Archive |
| `/emails/starred` | `GET` | Fetch starred emails |

### **Email Drafts**
| **Endpoint** | **Method** | **Description** |
|-------------|-----------|----------------|
| `/emails/drafts/save` | `POST` | Save an email as a draft |
| `/emails/drafts/{email_id}` | `GET` | Fetch a saved draft |
| `/emails/drafts/{email_id}` | `PUT` | Update a saved draft |
| `/emails/drafts/delete/{email_id}` | `DELETE` | Delete a saved draft |

### **Email Actions**
| **Endpoint** | **Method** | **Description** |
|-------------|-----------|----------------|
| `/emails/reply/{email_id}` | `POST` | Reply to an email |
| `/emails/forward/{email_id}` | `POST` | Forward an email |
| `/emails/reply-all/{email_id}` | `POST` | Reply to all recipients of an email |
| `/emails/archive/{email_id}` | `POST` | Move an email to Archive folder |

### **Email Search and Filter**
| **Endpoint** | **Method** | **Description** |
|-------------|-----------|----------------|
| `/emails/search` | `GET` | Search emails based on a query |
| `/emails/filter` | `GET` | Filter emails based on a filter type |
| `/emails/unread/count` | `GET` | Get the count of unread emails |

### **Email Attachments**
| **Endpoint** | **Method** | **Description** |
|-------------|-----------|----------------|
| `/emails/attachments/{email_id}` | `GET` | Fetch attachments of a specific email |
| `/emails/attachment/{email_id}/{attachment_id}` | `GET` | Fetch a specific attachment of an email |
| `/emails/attachment/download/{email_id}/{attachment_id}` | `GET` | Download a specific attachment of an email |

### **WebSocket**
| **Endpoint** | **Method** | **Description** |
|-------------|-----------|----------------|
| `/ws` | `WS` | WebSocket for real-time updates |

### **Background Tasks**
| **Endpoint** | **Method** | **Description** |
|-------------|-----------|----------------|
| `/check-new-emails` | `POST` | Manually trigger background email check |

---

## **📜 License**
This project is licensed under the **MIT License**.

---

🚀 **Enjoy MailBridge!** 🚀
