from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Saga
from app.schemas import ReservationCreate, SagaOut, ChargeRequest
from app.services import saga as saga_svc
from app.services.idempotency import begin_idempotent_request, complete_idempotent_request, Replay

router = APIRouter(prefix="/reservations", tags=["reservations"])


def _require_key(idempotency_key: str | None) -> str:
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")
    return idempotency_key


@router.post("", response_model=SagaOut, status_code=201)
def create_reservation(
    body: ReservationCreate,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = _require_key(idempotency_key)
    endpoint = "POST /reservations"
    try:
        begin_idempotent_request(db, key, endpoint, body.model_dump())
    except Replay as r:
        return r.body

    try:
        result = saga_svc.reserve_stock(db, body.sku, body.qty, body.customer_id, body.amount_cents)
        out = SagaOut.model_validate(result).model_dump()
        complete_idempotent_request(db, key, endpoint, 201, out)
        db.commit()
        return out
    except HTTPException as e:
        complete_idempotent_request(db, key, endpoint, e.status_code, {"detail": e.detail})
        db.commit()
        raise


@router.post("/{saga_id}/charge", response_model=SagaOut)
def charge_reservation(
    saga_id: str,
    body: ChargeRequest,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = _require_key(idempotency_key)
    endpoint = f"POST /reservations/{saga_id}/charge"
    try:
        begin_idempotent_request(db, key, endpoint, body.model_dump())
    except Replay as r:
        return r.body

    s = db.get(Saga, saga_id)
    if s is None:
        complete_idempotent_request(db, key, endpoint, 404, {"detail": "unknown saga"})
        db.commit()
        raise HTTPException(status_code=404, detail="unknown saga")

    try:
        result = saga_svc.charge_payment(db, s, simulate_decline=body.simulate_decline)
        out = SagaOut.model_validate(result).model_dump()
        complete_idempotent_request(db, key, endpoint, 200, out)
        db.commit()
        return out
    except saga_svc.PaymentDeclined:
        out = SagaOut.model_validate(s).model_dump()
        complete_idempotent_request(db, key, endpoint, 402, out)
        db.commit()
        raise HTTPException(status_code=402, detail="payment declined; reservation released")
    except HTTPException as e:
        complete_idempotent_request(db, key, endpoint, e.status_code, {"detail": e.detail})
        db.commit()
        raise


@router.post("/{saga_id}/commit", response_model=SagaOut)
def commit_reservation(
    saga_id: str,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = _require_key(idempotency_key)
    endpoint = f"POST /reservations/{saga_id}/commit"
    try:
        begin_idempotent_request(db, key, endpoint, {})
    except Replay as r:
        return r.body

    s = db.get(Saga, saga_id)
    if s is None:
        complete_idempotent_request(db, key, endpoint, 404, {"detail": "unknown saga"})
        db.commit()
        raise HTTPException(status_code=404, detail="unknown saga")

    try:
        result = saga_svc.commit_saga(db, s)
        out = SagaOut.model_validate(result).model_dump()
        complete_idempotent_request(db, key, endpoint, 200, out)
        db.commit()
        return out
    except HTTPException as e:
        complete_idempotent_request(db, key, endpoint, e.status_code, {"detail": e.detail})
        db.commit()
        raise


@router.post("/{saga_id}/release", response_model=SagaOut)
def release_reservation(
    saga_id: str,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = _require_key(idempotency_key)
    endpoint = f"POST /reservations/{saga_id}/release"
    try:
        begin_idempotent_request(db, key, endpoint, {})
    except Replay as r:
        return r.body

    s = db.get(Saga, saga_id)
    if s is None:
        complete_idempotent_request(db, key, endpoint, 404, {"detail": "unknown saga"})
        db.commit()
        raise HTTPException(status_code=404, detail="unknown saga")

    try:
        result = saga_svc.release_saga(db, s)
        out = SagaOut.model_validate(result).model_dump()
        complete_idempotent_request(db, key, endpoint, 200, out)
        db.commit()
        return out
    except HTTPException as e:
        complete_idempotent_request(db, key, endpoint, e.status_code, {"detail": e.detail})
        db.commit()
        raise


@router.get("", response_model=list[SagaOut])
def list_reservations(db: Session = Depends(get_db)):
    return db.query(Saga).order_by(Saga.created_at.desc()).limit(500).all()


@router.get("/{saga_id}", response_model=SagaOut)
def get_reservation(saga_id: str, db: Session = Depends(get_db)):
    s = db.get(Saga, saga_id)
    if s is None:
        raise HTTPException(status_code=404, detail="unknown saga")
    return s
