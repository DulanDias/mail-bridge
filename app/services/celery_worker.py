from celery import Celery
import os

# Celery Configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery = Celery(
    "mailbridge",
    broker=REDIS_URL,
    backend=REDIS_URL,
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
