from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import LedgerEntry, Account
from app.schemas import LedgerEntryOut

router = APIRouter(prefix="/ledger", tags=["ledger"])


@router.get("/entries", response_model=list[LedgerEntryOut])
def list_entries(
    sku: str | None = Query(default=None),
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
):
    q = select(LedgerEntry).order_by(LedgerEntry.created_at.desc()).limit(limit)
    if sku:
        q = q.where(LedgerEntry.sku == sku)
    rows = db.execute(q).scalars().all()
    return [
        LedgerEntryOut(
            id=r.id, transaction_id=r.transaction_id, account_id=r.account_id,
            direction=r.direction.value, amount=r.amount, sku=r.sku,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


@router.get("/accounts")
def list_accounts(db: Session = Depends(get_db)):
    rows = db.execute(select(Account)).scalars().all()
    return [{"id": a.id, "name": a.name, "kind": a.kind.value} for a in rows]
