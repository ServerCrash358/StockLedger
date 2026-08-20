from sqlalchemy.orm import Session

from app.models import Account, LedgerEntry, Direction


def post_transfer(
    db: Session,
    transaction_id: str,
    debit_account: Account,
    credit_account: Account,
    amount: int,
    sku: str | None = None,
) -> None:
    """Write one balanced debit/credit pair. Never mutates existing rows —
    the ledger is append-only, so 'what happened' is always answerable from
    history rather than a status column concurrent writers could stomp."""
    db.add(LedgerEntry(
        transaction_id=transaction_id, account_id=debit_account.id,
        direction=Direction.DEBIT, amount=amount, sku=sku,
    ))
    db.add(LedgerEntry(
        transaction_id=transaction_id, account_id=credit_account.id,
        direction=Direction.CREDIT, amount=amount, sku=sku,
    ))
