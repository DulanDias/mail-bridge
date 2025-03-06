from app.config import redis_client

def store_mailbox_config(config):
    redis_client.set(f"mailbox_config:{config.email}", config.dict())

def get_mailbox_config(mailbox_email: str):
    config = redis_client.get(f"mailbox_config:{mailbox_email}")
    if not config:
        raise Exception("Mailbox not found")
    return eval(config)
