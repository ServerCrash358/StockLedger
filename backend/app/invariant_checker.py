"""Standalone process. Run separately from the API: `python -m app.invariant_checker`.

Deliberately out-of-process: a bug in the request-handling code path should not
be able to also suppress the alarm that would catch it. This process shares
only the database schema with the API, nothing else.
"""
import time
from datetime import datetime, timezone

from app.db import SessionLocal
from app.models import SystemState, InvariantViolation
from app.services.invariants import check_ledger_balances, check_stock_conservation

POLL_SECONDS = 2


def run_once() -> bool:
    db = SessionLocal()
    try:
        violations = check_ledger_balances(db) + check_stock_conservation(db)

        state = db.get(SystemState, 1)
        if state is None:
            state = SystemState(id=1, halted=False)
            db.add(state)

        if violations:
            detail = "; ".join(violations)
            db.add(InvariantViolation(kind="invariant_check", detail=detail))
            state.halted = True
            state.halted_reason = detail
            state.halted_at = datetime.now(timezone.utc)
            db.commit()
            print(f"[invariant_checker] HALTED: {detail}")
            return False

        if state.halted:
            # Do not auto-clear; a human should investigate and reset explicitly.
            pass
        db.commit()
        return True
    finally:
        db.close()


def main():
    print("[invariant_checker] starting, polling every", POLL_SECONDS, "s")
    while True:
        try:
            ok = run_once()
            print(f"[invariant_checker] check ok={ok} at {datetime.now(timezone.utc).isoformat()}")
        except Exception as exc:  # noqa: BLE001
            print(f"[invariant_checker] error during check: {exc}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
