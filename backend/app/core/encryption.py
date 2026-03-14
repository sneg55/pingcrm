"""Symmetric encryption for sensitive fields (tokens, sessions).

Uses Fernet (AES-128-CBC + HMAC-SHA256) via the ``cryptography`` library.
The key is read from the ``ENCRYPTION_KEY`` environment variable.

Usage in SQLAlchemy models::

    from app.core.encryption import EncryptedString

    class User(Base):
        token: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)

Generate a key::

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String, TypeDecorator

from app.core.config import settings


def _get_fernet() -> Fernet:
    key = settings.ENCRYPTION_KEY
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set. Generate one with: "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_value(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    return _get_fernet().decrypt(ciphertext.encode()).decode()


class EncryptedString(TypeDecorator):
    """SQLAlchemy type that transparently encrypts/decrypts string columns."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:  # noqa: ANN001
        if value is None:
            return None
        return encrypt_value(value)

    def process_result_value(self, value: str | None, dialect) -> str | None:  # noqa: ANN001
        if value is None:
            return None
        try:
            return decrypt_value(value)
        except (InvalidToken, RuntimeError):
            import logging
            logging.getLogger(__name__).error(
                "EncryptedString: failed to decrypt value — wrong key, missing ENCRYPTION_KEY, or unencrypted data"
            )
            return value
