# StockLedger

A provably-correct inventory reservation and payment settlement engine.
Overselling and balance drift are structurally impossible here, not just
handled carefully — see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the
design decisions and trade-offs.

## Stack

- **Backend**: FastAPI + SQLAlchemy + PostgreSQL (`backend/`)
- **Frontend**: React + Vite dashboard (`frontend/`)
- **Invariant checker**: standalone Python process (`backend/app/invariant_checker.py`)

## Setup

### 1. Database

```bash
docker compose up -d postgres
```

This starts Postgres with two databases: `stockledger` (app) and
`stockledger_test` (tests).

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate   # Windows; use `source .venv/bin/activate` on Unix
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

In a second terminal, start the invariant checker (it must run continuously,
separately from the API):

```bash
cd backend
python -m app.invariant_checker
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. It proxies `/api/*` to the backend on port 8000.

### 4. Run the tests

```bash
cd backend
pytest tests/ -v
```

`tests/test_invariants.py` is the important one: it fires 1000 real concurrent
purchase attempts (via a thread pool, real Postgres transactions) at 100 units
of stock and asserts exactly 100 succeed, plus a Hypothesis property test that
randomizes stock levels and attempt sequences.

### 5. Run the definition-of-done demo

With the API and invariant checker both running:

```bash
cd backend
python scripts/chaos_demo.py --stock 100 --attempts 1000
```

Expected output: exactly 100 successes, 900 correctly-rejected attempts,
`available: 0`, `reserved: 0`, ledger balanced, invariant checker not halted.

Or use the dashboard's **Chaos test** panel to fire concurrent purchases from
the browser and watch stock levels and the invariant badge update live.

## How to break it, and why you can't

These are the actual attacks you'd try against a naive implementation, and
why each one fails here.

**1. Fire 1000 concurrent buy requests at 100 units of stock, hoping for a race.**
Every reservation takes `SELECT ... FOR UPDATE` on that SKU's single row before
checking `available`. Postgres serializes concurrent transactions on that
lock: request #2 doesn't read `available` until request #1's transaction has
committed (or rolled back), so it always sees the post-decrement value. There
is no window where two transactions both read "1 available" and both proceed
— the read and the check-and-write happen inside the same lock hold. See
[`reserve_stock`](backend/app/services/saga.py).

**2. Retry a request that timed out, hoping to get charged/reserved twice.**
Every mutating endpoint requires an `Idempotency-Key`. The key is the primary
key (with the endpoint) of a table with a uniqueness constraint — only one
request with that key can ever execute the real logic; every retry either
blocks until the original finishes (if concurrent) or replays the stored
response verbatim (if the original already finished). See
[`idempotency.py`](backend/app/services/idempotency.py).

**3. Crash the payment step after stock is reserved, hoping to leak reserved
stock that's never sold and never released.**
The saga records its state (`RESERVED` → `CHARGED` → `COMMITTED` /
`ROLLED_BACK`) in the same database as the ledger. A payment decline runs its
compensating transaction (`reserved → warehouse`) in the same request that
discovered the decline — there's no separate reconciliation step to forget to
run. A crash between steps leaves the saga in a well-defined, still-queryable
state (`RESERVED` or `CHARGED`) rather than silently lost.

**4. Directly UPDATE `stock_items.available` to a value that doesn't match
reality, hoping nothing notices.**
The invariant checker is a separate process with no code path in common with
the API other than the schema. It polls every 2 seconds and checks
`reserved + available == total` for every SKU and `SUM(debits) == SUM(credits)`
per ledger transaction. A violation halts new writes (`system_state.halted`)
and every mutating endpoint checks that flag first. A bug that corrupts data
via the write path can't also silence the alarm, because the alarm doesn't
run in the write path.

**5. Manufacture stock or money out of nowhere by writing an unbalanced ledger
entry.**
`post_transfer` only ever writes a matched debit/credit pair — there's no
function in the codebase that writes a lone `LedgerEntry`. Even if one did
slip through (a bug, not an attack from outside), the invariant checker's
balance check would catch it on the next poll and halt the system before it
compounded.

**What this doesn't defend against**: a bug in the *business logic* that
computes the *correct* amount to charge (e.g., a pricing error) — the ledger
will faithfully and correctly record an incorrect number. Structural
correctness guarantees the bookkeeping can't drift from itself; it doesn't
replace testing that the bookkeeping reflects the real world.
