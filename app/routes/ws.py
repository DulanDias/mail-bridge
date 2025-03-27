from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from app.services.jwt_service import decode_jwt
import json

router = APIRouter()

active_connections = {}  # Track WebSockets per email

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str):
    """ WebSocket connection using mailbox_token """
    try:
        # Unpack all six values returned by decode_jwt
        email, _, _, _, _, _ = decode_jwt(token)
    except Exception as e:
        await websocket.close(code=4001)  # Close WebSocket with error code
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    await websocket.accept()

    if email not in active_connections:
        active_connections[email] = []
    active_connections[email].append(websocket)

    try:
        while True:
            await websocket.receive_text()  # Keep the connection alive
    except WebSocketDisconnect:
        active_connections[email].remove(websocket)
        if not active_connections[email]:
            del active_connections[email]

async def notify_clients(email: str, new_emails: list):
    """ Notify WebSocket clients when new emails arrive """
    if email in active_connections:
        for ws in active_connections[email]:
            try:
                await ws.send_json({"email": email, "new_emails": new_emails})
            except Exception:
                active_connections[email].remove(ws)
                if not active_connections[email]:
                    del active_connections[email]
