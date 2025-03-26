import jwt
from datetime import datetime, timedelta
import os

# Secret keys for JWT signing
JWT_SECRET = os.getenv("JWT_SECRET", "your_jwt_secret_key")
JWT_ALGORITHM = "HS256"  # Use "RS256" if using asymmetric keys
JWT_EXPIRATION_MINUTES = 15  # Set token expiration time (e.g., 15 minutes)

def generate_jwt(email: str, password: str, imap_server: str, smtp_server: str, imap_port: int = 993, smtp_port: int = 587) -> str:
    """ Generate a JWT token with credentials and server details """
    payload = {
        "email": email,
        "password": password,
        "imap_server": imap_server,
        "smtp_server": smtp_server,
        "imap_port": imap_port,
        "smtp_port": smtp_port,
        "exp": datetime.utcnow() + timedelta(minutes=JWT_EXPIRATION_MINUTES)  # Expiration time
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_jwt(token: str) -> tuple:
    """ Decode JWT token and retrieve credentials """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return (
            payload["email"],
            payload["password"],
            payload["imap_server"],
            payload["smtp_server"],
            payload["imap_port"],
            payload["smtp_port"]
        )
    except jwt.ExpiredSignatureError:
        raise Exception("Token has expired")
    except jwt.InvalidTokenError:
        raise Exception("Invalid token")
