import hashlib
import json
import time

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import IdempotencyKey


class Replay(Exception):
    """Raised to short-circuit a handler with a previously-recorded response."""

    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self.body = body


def _hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def begin_idempotent_request(db: Session, key: str, endpoint: str, payload: dict) -> None:
    """Claims the (key, endpoint) row for this request, or raises Replay if the
    request already completed, or blocks (via row lock) if it's in flight.

    The unique constraint on (key, endpoint) is what actually prevents two
    concurrent retries from both proceeding: only one INSERT wins."""
    req_hash = _hash(payload)

    try:
        db.add(IdempotencyKey(key=key, endpoint=endpoint, request_hash=req_hash, in_progress=True))
        db.flush()
        return  # we claimed it; caller proceeds to do the real work
    except IntegrityError:
        db.rollback()

    # Row already exists. Wait for it to settle (bounded), then decide.
    for _ in range(100):
        row = db.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.key == key, IdempotencyKey.endpoint == endpoint
            ).with_for_update()
        ).scalar_one_or_none()
        db.commit()  # release lock between polls
        if row is None:
            # Vanishingly unlikely race; retry claim.
            return begin_idempotent_request(db, key, endpoint, payload)
        if row.request_hash != req_hash:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key reused with a different request body",
            )
        if not row.in_progress:
            raise Replay(row.status_code or 200, json.loads(row.response_body or "{}"))
        time.sleep(0.05)

    raise HTTPException(status_code=409, detail="Original request with this key still in progress")


def complete_idempotent_request(db: Session, key: str, endpoint: str, status_code: int, body: dict) -> None:
    row = db.get(IdempotencyKey, (key, endpoint))
    if row is not None:
        row.in_progress = False
        row.status_code = status_code
        row.response_body = json.dumps(body, default=str)
