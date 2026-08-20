import random
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import StockItem, Saga, SagaState, SystemState
from app.services import accounts, ledger


class PaymentDeclined(Exception):
    pass


def check_not_halted(db: Session) -> None:
    state = db.get(SystemState, 1)
    if state is not None and state.halted:
        raise HTTPException(
            status_code=503,
            detail=f"System halted by invariant checker: {state.halted_reason}",
        )


def reserve_stock(db: Session, sku: str, qty: int, customer_id: str, amount_cents: int) -> Saga:
    """The oversell-prevention step. SELECT ... FOR UPDATE takes an exclusive
    lock on this SKU's single row: a concurrent reservation for the same SKU
    blocks here until this transaction commits, then re-reads the updated
    `available`. That makes check-then-act atomic without a second check."""
    check_not_halted(db)

    if qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be positive")

    item = db.execute(
        select(StockItem).where(StockItem.sku == sku).with_for_update()
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail=f"unknown SKU {sku}")

    if item.available < qty:
        raise HTTPException(status_code=409, detail=f"insufficient stock for {sku}: {item.available} available")

    item.available -= qty
    item.reserved += qty

    txn_id = str(uuid.uuid4())
    warehouse = accounts.warehouse_account(db, sku)
    reserved = accounts.reserved_account(db, sku)
    ledger.post_transfer(db, txn_id, debit_account=reserved, credit_account=warehouse, amount=qty, sku=sku)

    saga = Saga(sku=sku, qty=qty, customer_id=customer_id, amount_cents=amount_cents, state=SagaState.RESERVED)
    db.add(saga)
    db.flush()
    return saga


def charge_payment(db: Session, saga: Saga, simulate_decline: bool = False) -> Saga:
    """Charges the customer's account. On decline, immediately compensates by
    releasing the reservation in the SAME request — no separate reconciliation
    step is needed because the ledger already has everything required to
    reverse itself."""
    check_not_halted(db)

    if saga.state != SagaState.RESERVED:
        raise HTTPException(status_code=409, detail=f"saga {saga.id} is in state {saga.state}, expected RESERVED")

    if simulate_decline:
        _release_reservation(db, saga)
        saga.state = SagaState.ROLLED_BACK
        saga.failure_reason = "payment_declined"
        db.flush()
        raise PaymentDeclined(f"payment declined for saga {saga.id}")

    txn_id = str(uuid.uuid4())
    customer = accounts.customer_account(db, saga.customer_id)
    in_flight = accounts.in_flight_account(db)
    ledger.post_transfer(db, txn_id, debit_account=in_flight, credit_account=customer, amount=saga.amount_cents)

    saga.state = SagaState.CHARGED
    db.flush()
    return saga


def commit_saga(db: Session, saga: Saga) -> Saga:
    """Settles both legs: moves reserved stock to sold, and in-flight payment
    to revenue. Both ledger writes happen in one DB transaction, so they are
    atomic with respect to any concurrent reader (including the invariant
    checker)."""
    check_not_halted(db)

    if saga.state != SagaState.CHARGED:
        raise HTTPException(status_code=409, detail=f"saga {saga.id} is in state {saga.state}, expected CHARGED")

    stock_txn = str(uuid.uuid4())
    reserved = accounts.reserved_account(db, saga.sku)
    sold = accounts.sold_account(db, saga.sku)
    ledger.post_transfer(db, stock_txn, debit_account=sold, credit_account=reserved, amount=saga.qty, sku=saga.sku)

    money_txn = str(uuid.uuid4())
    in_flight = accounts.in_flight_account(db)
    revenue = accounts.revenue_account(db)
    ledger.post_transfer(db, money_txn, debit_account=revenue, credit_account=in_flight, amount=saga.amount_cents)

    item = db.execute(
        select(StockItem).where(StockItem.sku == saga.sku).with_for_update()
    ).scalar_one()
    item.reserved -= saga.qty

    saga.state = SagaState.COMMITTED
    db.flush()
    return saga


def _release_reservation(db: Session, saga: Saga) -> None:
    item = db.execute(
        select(StockItem).where(StockItem.sku == saga.sku).with_for_update()
    ).scalar_one()
    item.reserved -= saga.qty
    item.available += saga.qty

    txn_id = str(uuid.uuid4())
    warehouse = accounts.warehouse_account(db, saga.sku)
    reserved = accounts.reserved_account(db, saga.sku)
    ledger.post_transfer(db, txn_id, debit_account=warehouse, credit_account=reserved, amount=saga.qty, sku=saga.sku)


def release_saga(db: Session, saga: Saga, reason: str = "manual_release") -> Saga:
    if saga.state not in (SagaState.RESERVED, SagaState.CHARGED):
        raise HTTPException(status_code=409, detail=f"saga {saga.id} cannot be released from state {saga.state}")

    if saga.state == SagaState.CHARGED:
        txn_id = str(uuid.uuid4())
        customer = accounts.customer_account(db, saga.customer_id)
        in_flight = accounts.in_flight_account(db)
        ledger.post_transfer(db, txn_id, debit_account=customer, credit_account=in_flight, amount=saga.amount_cents)

    _release_reservation(db, saga)
    saga.state = SagaState.ROLLED_BACK
    saga.failure_reason = reason
    db.flush()
    return saga
