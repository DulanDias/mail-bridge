from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@limiter.limit("10 per minute")
def rate_limited_request():
    """ Rate limits API calls to prevent abuse """
    return {"message": "Request processed"}
