from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json

router = APIRouter()

active_connections = {}  # Track WebSockets per email

@router.websocket("/")
async def websocket_endpoint(websocket: WebSocket):
    """ WebSocket connection for multiple mailboxes """
    await websocket.accept()
    message = await websocket.receive_text()
    mailbox_emails = json.loads(message).get("emails", [])

    for email in mailbox_emails:
        if email not in active_connections:
            active_connections[email] = []
        active_connections[email].append(websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        for email in mailbox_emails:
            active_connections[email].remove(websocket)
            if not active_connections[email]:
                del active_connections[email]

async def notify_clients(email: str, new_emails: list):
    """ Notify WebSocket clients when new emails arrive """
    if email in active_connections:
        for ws in active_connections[email]:
            await ws.send_json({"email": email, "new_emails": new_emails})
