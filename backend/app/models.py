import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Integer, BigInteger, DateTime, ForeignKey, Enum, Boolean, Text,
    UniqueConstraint, CheckConstraint,
)
from sqlalchemy.orm import relationship

from app.db import Base


def _now():
    return datetime.now(timezone.utc)


def _uuid():
    return str(uuid.uuid4())


class AccountKind(str, enum.Enum):
    STOCK = "stock"
    MONEY = "money"


class Direction(str, enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class SagaState(str, enum.Enum):
    RESERVED = "RESERVED"
    CHARGED = "CHARGED"
    COMMITTED = "COMMITTED"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED = "FAILED"


class StockItem(Base):
    __tablename__ = "stock_items"

    sku = Column(String, primary_key=True)
    total = Column(Integer, nullable=False)
    available = Column(Integer, nullable=False)
    reserved = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("available >= 0", name="ck_available_nonneg"),
        CheckConstraint("reserved >= 0", name="ck_reserved_nonneg"),
        CheckConstraint("available + reserved <= total", name="ck_conservation"),
    )


class Account(Base):
    __tablename__ = "accounts"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, unique=True, nullable=False)
    kind = Column(Enum(AccountKind), nullable=False)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id = Column(String, primary_key=True, default=_uuid)
    transaction_id = Column(String, nullable=False, index=True)
    account_id = Column(String, ForeignKey("accounts.id"), nullable=False)
    direction = Column(Enum(Direction), nullable=False)
    amount = Column(BigInteger, nullable=False)  # units for stock accounts, cents for money
    sku = Column(String, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_amount_positive"),
    )


class Saga(Base):
    __tablename__ = "sagas"

    id = Column(String, primary_key=True, default=_uuid)
    sku = Column(String, nullable=False, index=True)
    qty = Column(Integer, nullable=False)
    customer_id = Column(String, nullable=False)
    amount_cents = Column(BigInteger, nullable=False)
    state = Column(Enum(SagaState), nullable=False, default=SagaState.RESERVED)
    failure_reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key = Column(String, primary_key=True)
    endpoint = Column(String, primary_key=True)
    request_hash = Column(String, nullable=False)
    status_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    in_progress = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)


class InvariantViolation(Base):
    __tablename__ = "invariant_violations"

    id = Column(String, primary_key=True, default=_uuid)
    kind = Column(String, nullable=False)
    detail = Column(Text, nullable=False)
    detected_at = Column(DateTime(timezone=True), default=_now, nullable=False)


class SystemState(Base):
    __tablename__ = "system_state"

    id = Column(Integer, primary_key=True, default=1)
    halted = Column(Boolean, nullable=False, default=False)
    halted_reason = Column(Text, nullable=True)
    halted_at = Column(DateTime(timezone=True), nullable=True)
