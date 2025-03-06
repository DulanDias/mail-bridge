# **📧 MailBridge - FastAPI Mailbox Backend**
🚀 **MailBridge** is a powerful, scalable, and feature-rich **email management backend** built with **FastAPI**, **Redis**, **Celery**, and **WebSockets**. It allows seamless management of multiple mailboxes, real-time email notifications, and background email processing.

---

## **📖 Features**
✅ **Multiple Mailboxes Support** – Manage multiple email accounts dynamically.  
✅ **IMAP & SMTP Integration** – Fetch, send, delete, archive emails.  
✅ **Real-time Email Updates** – Uses **WebSockets** for live email notifications.  
✅ **Background Email Polling** – Uses **Celery** for periodic email updates.  
✅ **Unread Email Counters** – Cached unread email counts per mailbox.  
✅ **Email Metadata Handling** – Extract sender name, subject, recipients, CC, and BCC.  
✅ **Read Receipts Support** – Track read receipts if supported by IMAP.  
✅ **Rich Text & Inline Attachments** – Supports HTML email bodies and inline images.  
✅ **WebSocket over HTTP & HTTPS** – Supports **WS and WSS** with reverse proxy integration.  
✅ **Comprehensive Swagger API Docs** – Auto-generated API documentation.  
✅ **Docker & Docker Compose Support** – Easily deployable with Redis and Celery.  

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
git clone https://github.com/yourusername/mailbridge.git
cd mailbridge
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
| **Endpoint** | **Method** | **Description** |
|-------------|-----------|----------------|
| `/api/v1/mailbox/config` | `POST` | Configure a mailbox (IMAP/SMTP) |
| `/api/v1/mailbox/emails` | `GET` | Fetch paginated email list |
| `/api/v1/mailbox/send` | `POST` | Send an email (with attachments) |
| `/api/v1/mailbox/delete` | `POST` | Delete an email (move to trash) |
| `/api/v1/mailbox/mark-read` | `POST` | Mark an email as read |
| `/api/v1/mailbox/mark-unread` | `POST` | Mark an email as unread |
| `/api/v1/mailbox/archive` | `POST` | Archive an email |
| `/api/v1/mailbox/ws` | `WS` | WebSocket for real-time updates |

---

## **📜 License**
This project is licensed under the **MIT License**.

---

🚀 **Enjoy MailBridge!** 🚀
