from fastapi import FastAPI
from app.routes import mailbox, auth, ws, tasks

app = FastAPI(
    title="MailBridge API",
    version="1.0",
    description="A powerful email management backend with real-time updates, email metadata handling, and advanced email features."
)

# Include API routes
app.include_router(mailbox.router, prefix="/api/v1/mailbox", tags=["Mailbox"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(ws.router, prefix="/api/v1/ws", tags=["WebSocket"])
app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["Background Tasks"])

@app.get("/")
def root():
    return {"message": "Welcome to MailBridge API!"}
