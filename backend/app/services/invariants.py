from sqlalchemy import func, select, case
from sqlalchemy.orm import Session

from app.models import LedgerEntry, Direction, StockItem


def check_ledger_balances(db: Session) -> list[str]:
    """SUM(debits) must equal SUM(credits) for every transaction_id. Money is
    never created or destroyed, only moved between accounts."""
    rows = db.execute(
        select(
            LedgerEntry.transaction_id,
            func.sum(case((LedgerEntry.direction == Direction.DEBIT, LedgerEntry.amount), else_=0)),
            func.sum(case((LedgerEntry.direction == Direction.CREDIT, LedgerEntry.amount), else_=0)),
        ).group_by(LedgerEntry.transaction_id)
    ).all()

    violations = []
    for txn_id, debits, credits in rows:
        if debits != credits:
            violations.append(f"transaction {txn_id} unbalanced: debits={debits} credits={credits}")
    return violations


def check_stock_conservation(db: Session) -> list[str]:
    """reserved + available must never exceed total for any SKU."""
    rows = db.execute(select(StockItem)).scalars().all()
    violations = []
    for item in rows:
        if item.available < 0 or item.reserved < 0:
            violations.append(f"SKU {item.sku} has negative stock: available={item.available} reserved={item.reserved}")
        if item.available + item.reserved > item.total:
            violations.append(
                f"SKU {item.sku} conservation broken: available={item.available} reserved={item.reserved} total={item.total}"
            )
    return violations
