import jwt
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
import os
import base64

# Secret keys for encryption and JWT signing
JWT_SECRET = os.getenv("JWT_SECRET", "your_jwt_secret_key")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "your_32_byte_encryption_key").encode()

def encrypt_credentials(email: str, password: str) -> str:
    """ Encrypt email and password using AES-GCM """
    cipher = Cipher(algorithms.AES(ENCRYPTION_KEY), modes.GCM(os.urandom(12)), backend=default_backend())
    encryptor = cipher.encryptor()
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(f"{email}:{password}".encode()) + padder.finalize()
    encrypted = encryptor.update(padded_data) + encryptor.finalize()
    return base64.b64encode(cipher.iv + encryptor.tag + encrypted).decode()

def decrypt_credentials(encrypted_data: str) -> tuple:
    """ Decrypt email and password from AES-GCM encrypted data """
    data = base64.b64decode(encrypted_data)
    iv, tag, encrypted = data[:12], data[12:28], data[28:]
    cipher = Cipher(algorithms.AES(ENCRYPTION_KEY), modes.GCM(iv, tag), backend=default_backend())
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(encrypted) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    unpadded_data = unpadder.update(decrypted) + unpadded_data.finalize()
    email, password = unpadded_data.decode().split(":")
    return email, password

def generate_jwt(email: str, password: str, imap_server: str, smtp_server: str, imap_port: int = 993, smtp_port: int = 587) -> str:
    """ Generate a JWT token with encrypted credentials and server details """
    encrypted_credentials = encrypt_credentials(email, password)
    payload = {
        "credentials": encrypted_credentials,
        "imap_server": imap_server,
        "smtp_server": smtp_server,
        "imap_port": imap_port,
        "smtp_port": smtp_port
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def decode_jwt(token: str) -> tuple:
    """ Decode JWT token and decrypt credentials """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        encrypted_credentials = payload["credentials"]
        email, password = decrypt_credentials(encrypted_credentials)
        return email, password, payload["imap_server"], payload["smtp_server"], payload["imap_port"], payload["smtp_port"]
    except jwt.ExpiredSignatureError:
        raise Exception("Token has expired")
    except jwt.InvalidTokenError:
        raise Exception("Invalid token")
