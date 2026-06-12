import datetime
from typing import Optional
from cryptography.fernet import Fernet
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


class TimestampMixin:
    """Mixin to add audit timestamp fields and soft delete."""
    
    created_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False
    )
    deleted_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
        default=None
    )


class EncryptedString(sa.types.TypeDecorator):
    """SQLAlchemy TypeDecorator for symmetric encryption of sensitive string data.
    
    Uses Cryptography Fernet (AES-128 key length in CBC mode, HMAC authentication)
    to encrypt string fields transparently before saving to DB, and decrypts them on read.
    """
    impl = sa.Text
    cache_ok = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Load the base64-encoded key from settings
        key = settings.ENCRYPTION_KEY.encode()
        self.fernet = Fernet(key)

    def process_bind_param(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None:
            return None
        return self.fernet.encrypt(value.encode()).decode()

    def process_result_value(self, value: Optional[str], dialect) -> Optional[str]:
        if value is None:
            return None
        try:
            return self.fernet.decrypt(value.encode()).decode()
        except Exception as e:
            # Fallback or raise error in case of decryption failure
            raise ValueError(f"Failed to decrypt database value: {e}")
