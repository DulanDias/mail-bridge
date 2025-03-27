from celery import Celery
import os

# Celery Configuration
celery = Celery(
    "mailbridge",
    include=["app.services.email_service"]
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

if __name__ == "__main__":
    celery.start()
