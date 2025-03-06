import redis
import os

# Redis Connection
redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)

# Default IMAP/SMTP settings for custom mailboxes
DEFAULT_IMAP_PORT = 993
DEFAULT_SMTP_PORT = 587
