"""Property-based + concurrency tests. These are the tests that actually
exercise the claim in the architecture doc: that SELECT ... FOR UPDATE row
locking on stock_items prevents oversell under real concurrent interleaving,
and that the ledger stays balanced no matter how operations interleave.

Requires a running Postgres reachable at TEST_DATABASE_URL (defaults to
postgresql+psycopg://stockledger:stockledger@localhost:5432/stockledger_test).
"""
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from hypothesis import given, settings, strategies as st, HealthCheck
from fastapi import HTTPException

from app.models import StockItem
from app.services import saga as saga_svc
from app.services.invariants import check_ledger_balances, check_stock_conservation


def _fresh_sku(session_factory, total: int) -> str:
    sku = f"sku-{uuid.uuid4().hex[:8]}"
    db = session_factory()
    try:
        db.add(StockItem(sku=sku, total=total, available=total, reserved=0))
        db.commit()
    finally:
        db.close()
    return sku


def _attempt_purchase(session_factory, sku: str, qty: int) -> bool:
    """One full reserve->charge->commit cycle in its own session/transaction,
    mimicking an independent concurrent request."""
    db = session_factory()
    try:
        s = saga_svc.reserve_stock(db, sku, qty, f"cust-{uuid.uuid4()}", amount_cents=qty * 500)
        db.commit()
    except HTTPException:
        db.rollback()
        return False
    finally:
        pass

    try:
        saga_svc.charge_payment(db, s)
        saga_svc.commit_saga(db, s)
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()


def test_concurrent_purchases_never_oversell(session_factory):
    """100 units of stock, 1000 concurrent purchase attempts of 1 unit each:
    exactly 100 must succeed."""
    total_stock = 100
    num_attempts = 1000
    sku = _fresh_sku(session_factory, total_stock)

    results = []
    with ThreadPoolExecutor(max_workers=50) as pool:
        futures = [pool.submit(_attempt_purchase, session_factory, sku, 1) for _ in range(num_attempts)]
        for f in as_completed(futures):
            results.append(f.result())

    successes = sum(1 for r in results if r)
    assert successes == total_stock, f"expected exactly {total_stock} successes, got {successes}"

    db = session_factory()
    try:
        item = db.get(StockItem, sku)
        assert item.available == 0
        assert item.reserved == 0
        assert item.available + item.reserved <= item.total

        assert check_ledger_balances(db) == []
        assert check_stock_conservation(db) == []
    finally:
        db.close()


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    total_stock=st.integers(min_value=1, max_value=20),
    attempts=st.lists(st.integers(min_value=1, max_value=5), min_size=1, max_size=30),
)
def test_random_interleaved_reservations_hold_invariants(session_factory, total_stock, attempts):
    """For a randomized stock level and randomized sequence of concurrent
    reservation sizes, the invariants must hold and total successful
    reservations must never exceed initial stock."""
    sku = _fresh_sku(session_factory, total_stock)

    def attempt(qty):
        db = session_factory()
        try:
            s = saga_svc.reserve_stock(db, sku, qty, f"cust-{uuid.uuid4()}", amount_cents=qty * 100)
            db.commit()
            return qty
        except HTTPException:
            db.rollback()
            return 0
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=10) as pool:
        reserved_units = list(pool.map(attempt, attempts))

    assert sum(reserved_units) <= total_stock

    db = session_factory()
    try:
        item = db.get(StockItem, sku)
        assert item.available >= 0
        assert item.reserved >= 0
        assert item.available + item.reserved <= item.total
        assert check_stock_conservation(db) == []
        assert check_ledger_balances(db) == []
    finally:
        db.close()


def test_payment_decline_releases_reservation(session_factory):
    sku = _fresh_sku(session_factory, 10)
    db = session_factory()
    try:
        s = saga_svc.reserve_stock(db, sku, 3, "cust-1", amount_cents=1500)
        db.commit()

        try:
            saga_svc.charge_payment(db, s, simulate_decline=True)
            assert False, "expected PaymentDeclined"
        except saga_svc.PaymentDeclined:
            db.commit()

        item = db.get(StockItem, sku)
        assert item.available == 10
        assert item.reserved == 0
        assert check_ledger_balances(db) == []
    finally:
        db.close()


def test_idempotent_retry_does_not_double_reserve(session_factory):
    from app.services.idempotency import begin_idempotent_request, complete_idempotent_request, Replay

    sku = _fresh_sku(session_factory, 10)
    endpoint = "POST /reservations"
    payload = {"sku": sku, "qty": 2, "customer_id": "c1", "amount_cents": 1000}
    key = str(uuid.uuid4())

    db = session_factory()
    try:
        begin_idempotent_request(db, key, endpoint, payload)
        s = saga_svc.reserve_stock(db, sku, 2, "c1", 1000)
        complete_idempotent_request(db, key, endpoint, 201, {"id": s.id, "state": s.state.value})
        db.commit()
    finally:
        db.close()

    db2 = session_factory()
    try:
        try:
            begin_idempotent_request(db2, key, endpoint, payload)
            assert False, "expected Replay on retry"
        except Replay as r:
            assert r.status_code == 201
        db2.rollback()

        item = db2.get(StockItem, sku)
        assert item.available == 8  # only reserved once, not twice
    finally:
        db2.close()
