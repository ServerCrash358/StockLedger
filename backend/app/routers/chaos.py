import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import saga as saga_svc
from app.schemas import SagaOut

router = APIRouter(prefix="/chaos", tags=["chaos"])


class PurchaseRequest(BaseModel):
    sku: str
    amount_cents: int = 1000


class PurchaseResult(BaseModel):
    ok: bool
    saga: SagaOut | None = None
    error: str | None = None


@router.post("/purchase", response_model=PurchaseResult)
def one_shot_purchase(body: PurchaseRequest, db: Session = Depends(get_db)):
    """Convenience endpoint for the dashboard's chaos button: runs the full
    reserve -> charge -> commit sequence for qty=1 as one call, so the UI can
    fire N of these concurrently to demonstrate no-oversell without needing to
    orchestrate three round-trips per simulated buyer."""
    customer_id = f"chaos-{uuid.uuid4()}"
    try:
        s = saga_svc.reserve_stock(db, body.sku, 1, customer_id, body.amount_cents)
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return PurchaseResult(ok=False, error=str(exc))

    try:
        saga_svc.charge_payment(db, s)
        saga_svc.commit_saga(db, s)
        db.commit()
        return PurchaseResult(ok=True, saga=SagaOut.model_validate(s))
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return PurchaseResult(ok=False, error=str(exc), saga=None)
