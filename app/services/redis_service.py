import json
from app.config import redis_client

def store_mailbox_config(config):
    """ Store mailbox config in Redis (serialize to JSON) """
    redis_client.set(f"mailbox_config:{config.email}", json.dumps(config.dict()))

def get_mailbox_config(mailbox_email: str):
    """ Retrieve mailbox config from Redis (deserialize from JSON) """
    config = redis_client.get(f"mailbox_config:{mailbox_email}")
    if not config:
        raise Exception("Mailbox not found")
    return json.loads(config)
