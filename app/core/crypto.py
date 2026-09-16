import base64
import hashlib
import hmac
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from dotenv import load_dotenv


load_dotenv()


def _load_master_key() -> bytes:
    encoded_key = os.getenv("MOTH_DB_KEY")

    if not encoded_key:
        raise RuntimeError("MOTH_DB_KEY is missing")

    key = base64.urlsafe_b64decode(encoded_key)

    if len(key) != 32:
        raise RuntimeError("MOTH_DB_KEY must decode to 32 bytes")

    return key


def _derive_key(purpose: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=purpose,
    ).derive(_load_master_key())


ENCRYPTION_KEY = _derive_key(b"MOTH flag encryption")
FINGERPRINT_KEY = _derive_key(b"MOTH flag fingerprinting")


def encrypt_flag(flag: str) -> tuple[bytes, bytes]:
    nonce = os.urandom(12)

    aes = AESGCM(ENCRYPTION_KEY)
    ciphertext = aes.encrypt(
        nonce,
        flag.encode("utf-8"),
        None,
    )

    return nonce, ciphertext


def decrypt_flag(nonce: bytes, ciphertext: bytes) -> str:
    aes = AESGCM(ENCRYPTION_KEY)

    plaintext = aes.decrypt(
        nonce,
        ciphertext,
        None,
    )

    return plaintext.decode("utf-8")


def fingerprint_flag(flag: str) -> str:
    return hmac.new(
        FINGERPRINT_KEY,
        flag.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()