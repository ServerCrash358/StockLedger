from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import SystemState
from app.schemas import HealthOut
from app.services.invariants import check_ledger_balances, check_stock_conservation

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthOut)
def health(db: Session = Depends(get_db)):
    state = db.get(SystemState, 1)
    ledger_violations = check_ledger_balances(db)
    stock_violations = check_stock_conservation(db)
    return HealthOut(
        halted=bool(state and state.halted),
        halted_reason=state.halted_reason if state else None,
        last_checked=state.halted_at.isoformat() if state and state.halted_at else None,
        ledger_balanced=len(ledger_violations) == 0,
        stock_conserved=len(stock_violations) == 0,
    )


@router.post("/reset")
def reset_halt(db: Session = Depends(get_db)):
    """Manual override for operators after investigating a halt. Not exposed
    to the chaos-test UI on purpose — clearing a halt should be a deliberate
    human action, never automatic."""
    state = db.get(SystemState, 1)
    if state:
        state.halted = False
        state.halted_reason = None
        db.commit()
    return {"halted": False}
