from fastapi import APIRouter
from app.services import email_service

router = APIRouter()

@router.post("/check-new-emails")
async def trigger_email_check(mailbox_email: str):
    """ Trigger background email check """
    email_service.check_new_emails.delay(mailbox_email)
    return {"message": "Background email check started"}
