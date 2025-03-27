import jwt
from datetime import datetime, timedelta
import os
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Secret keys for JWT signing
JWT_SECRET = os.getenv("JWT_SECRET", "your_jwt_secret_key")
JWT_ALGORITHM = "HS256"  # Use "RS256" if using asymmetric keys
JWT_EXPIRATION_MINUTES = 15  # Set token expiration time (e.g., 15 minutes)
JWT_REFRESH_EXPIRATION_DAYS = 7  # Set refresh token expiration time (e.g., 7 days)

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
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    logging.debug(f"Generated JWT: {token}")
    return token

def decode_jwt(token: str) -> tuple:
    """ Decode JWT token and retrieve credentials """
    try:
        logging.debug(f"Decoding JWT token: {token}")
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        logging.debug(f"Decoded JWT payload: {payload}")
        return (
            payload["email"],
            payload["password"],
            payload["imap_server"],
            payload["smtp_server"],
            payload["imap_port"],
            payload["smtp_port"]
        )
    except jwt.ExpiredSignatureError:
        logging.error("Token has expired")
        raise Exception("Token has expired")
    except jwt.InvalidTokenError as e:
        logging.error(f"Invalid token: {str(e)}")
        raise Exception("Invalid token")

def generate_refresh_token(email: str, password: str, imap_server: str, smtp_server: str, imap_port: int = 993, smtp_port: int = 587) -> str:
    """ Generate a refresh token with credentials and server details """
    payload = {
        "email": email,
        "password": password,
        "imap_server": imap_server,
        "smtp_server": smtp_server,
        "imap_port": imap_port,
        "smtp_port": smtp_port,
        "exp": datetime.utcnow() + timedelta(days=JWT_REFRESH_EXPIRATION_DAYS)  # Expiration time
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    logging.debug(f"Generated Refresh Token: {token}")
    return token

def decode_refresh_token(token: str) -> tuple:
    """ Decode refresh token and retrieve credentials """
    try:
        logging.debug(f"Decoding Refresh Token: {token}")
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        logging.debug(f"Decoded Refresh Token Payload: {payload}")
        return (
            payload["email"],
            payload["password"],
            payload["imap_server"],
            payload["smtp_server"],
            payload["imap_port"],
            payload["smtp_port"]
        )
    except jwt.ExpiredSignatureError:
        logging.error("Refresh token has expired")
        raise Exception("Refresh token has expired")
    except jwt.InvalidTokenError as e:
        logging.error(f"Invalid refresh token: {str(e)}")
        raise Exception("Invalid refresh token")
