# StockLedger — Architecture

## Problem

Two independent classes of bugs cause real money/inventory loss in e-commerce systems:

1. **Oversell**: two concurrent requests both read `available_stock = 1`, both decide to
   proceed, both decrement — stock goes negative or is sold twice.
2. **Balance drift**: a payment is charged but the reservation that provoked it never
   committed (or vice versa), because the two operations happen against different
   systems (inventory DB, payment gateway) with no atomic boundary between them, and a
   retried request re-runs a side effect that already happened.

Both are concurrency/consistency bugs, not business-logic bugs. The fix has to be
structural: make the invalid states unrepresentable, not "be careful in the handler."

## Design decisions

### 1. Double-entry ledger for both stock and money

Every state change is a **transfer between two accounts**, recorded as a balanced pair
of rows in an append-only `ledger_entries` table:

```
ledger_entries(id, transaction_id, account_id, direction[debit|credit], amount, created_at)
```

- Stock accounts: every SKU has a `warehouse:<sku>`, `reserved:<sku>`, and `sold:<sku>`
  account. Reserving stock is a transfer `warehouse → reserved`. Committing a sale is
  `reserved → sold`. Releasing a reservation is `reserved → warehouse`. The sum of unit
  counts across all three accounts for a SKU is invariant — units are moved, never
  created or destroyed.
- Money accounts: `customer:<id>`, `revenue`, `payments_in_flight`. A charge is
  `customer → payments_in_flight`; settlement is `payments_in_flight → revenue`.

**Why this design**: because entries are never mutated or deleted, "did this operation
happen" is answerable by querying immutable history instead of trusting a mutable
`status` column that concurrent writers could stomp. It also gives the invariant checker
a trivial, cheap check: `SUM(debits) == SUM(credits)` per transaction and per account
family. This is the same reason accounting systems have used double-entry bookkeeping
for 500 years — it makes a whole category of arithmetic errors self-detecting.

### 2. Two-phase saga: reserve → charge → commit/compensate

```
POST /reservations        -> reserve stock (warehouse -> reserved), state=RESERVED
POST /reservations/{id}/charge -> charge payment (customer -> in_flight), state=CHARGED
POST /reservations/{id}/commit -> settle both legs, state=COMMITTED
   on failure at any step -> compensating transaction reverses prior steps, state=ROLLED_BACK
```

Each step is its own DB transaction against `ledger_entries` — never a single
distributed transaction across "inventory" and "payment," because in this
implementation both live in the same Postgres instance, so the saga is really a state
machine over one database, sequenced through explicit steps recorded in a `sagas` table.
The `sagas.state` column is the single source of truth for where a given order is in the
flow; compensating actions are just more ledger entries, not deletions.

**Why saga over a single 2PC transaction**: even inside one database, holding a
transaction open across an external payment gateway call would hold row locks for
network-latency durations, serializing all traffic against that SKU. Splitting into
steps, each short-lived and independently retriable, keeps lock hold time to
milliseconds.

### 3. Concurrency control: `SELECT ... FOR UPDATE` on the stock row, not SERIALIZABLE

The reservation step does:

```sql
BEGIN;
SELECT available FROM stock_items WHERE sku = $1 FOR UPDATE;
-- application checks available >= qty
UPDATE stock_items SET available = available - qty, reserved = reserved + qty WHERE sku = $1;
INSERT INTO ledger_entries (...) -- balanced debit/credit pair
COMMIT;
```

`FOR UPDATE` takes an exclusive row lock on the specific `stock_items` row for the SKU
being purchased at `READ COMMITTED` isolation. Concurrent reservations for the **same**
SKU serialize on that one row: the second transaction blocks at `SELECT FOR UPDATE`
until the first commits or rolls back, then re-reads the now-updated `available` value.
This makes "check-then-act" atomic without re-checking after the fact.

**Why not `SERIALIZABLE`**: `SERIALIZABLE` would also prevent the anomaly (it detects
the write skew and aborts one transaction), but it does so optimistically — both
transactions proceed, and one is aborted at commit time with a serialization-failure
error that the client must retry. Under heavy contention on a single hot SKU (exactly
the "flash sale" scenario this system targets), that produces a storm of aborts and
retries, wasting work. `SELECT FOR UPDATE` instead makes the second transaction *wait*
rather than *fail*, which is strictly better when the contention is expected and
concentrated on one row: no wasted work, no retry storm, and throughput is bounded by
lock hold time (a few milliseconds) rather than by abort-and-retry latency.
`SERIALIZABLE` would be the right choice if contention were spread unpredictably across
many rows/tables where explicit locking isn't practical — it isn't, here.

Row locks are scoped to `stock_items` (one row per SKU), so reservations for
**different** SKUs never block each other — the lock is exactly as coarse as it needs
to be and no coarser.

### 4. Idempotency keys

Every mutating endpoint (`POST /reservations`, `.../charge`, `.../commit`) requires an
`Idempotency-Key` header. The key, request-body hash, endpoint, and eventual response
are stored in an `idempotency_keys` table with a unique constraint on
`(key, endpoint)`. On retry with the same key:

- if the original request is still in flight, the retry blocks (row lock again) rather
  than racing it;
- if it completed, the stored response is replayed verbatim — no new ledger entries are
  written, so no double charge/reserve.

**Why store the response, not just a dedup flag**: a bare dedup flag tells the client
"already done" but not *what* happened (e.g., which reservation ID was created), forcing
them to guess or re-derive state. Storing and replaying the actual response makes
retries behave exactly like the original call from the client's point of view.

### 5. Background invariant checker as a separate process

A standalone worker (`app/services/invariant_checker.py`, run as its own process) polls
every N seconds and asserts, in a read-only transaction:

- `SUM(debit amounts) == SUM(credit amounts)` for every `transaction_id` in
  `ledger_entries` (the ledger balances).
- `reserved + available == total` for every row in `stock_items` (stock is conserved).

On violation it writes an `invariant_violations` row, flips a `system_halted` flag that
the API checks before accepting new mutating requests, and the failure is surfaced on
the dashboard. It runs **out-of-process** so a bug in request-handling code cannot also
suppress the alarm that would catch it — the checker has no code path in common with the
write path other than the schema itself.

### 6. Property-based testing

`tests/test_invariants.py` uses Hypothesis to generate randomized sequences of
concurrent reserve/charge/commit/release operations against random SKUs and quantities,
run through a thread pool to force real interleaving against Postgres, and asserts the
two invariants above hold after every sequence, plus that total successful reservations
for a SKU never exceed its initial stock. This tests the *interleaving*, not just the
single-request logic — the bug class this project exists to rule out only appears under
concurrency, so the tests must create concurrency.

## Data model summary

```
stock_items(sku PK, total, available, reserved)
accounts(id PK, name UNIQUE, kind[stock|money])
ledger_entries(id PK, transaction_id, account_id FK, direction, amount, sku, created_at)
sagas(id PK, sku, qty, customer_id, amount_cents, state, created_at, updated_at)
idempotency_keys(key, endpoint, request_hash, response_body, status_code, created_at, PK(key, endpoint))
invariant_violations(id PK, kind, detail, detected_at)
system_state(id PK, halted BOOLEAN, halted_reason, halted_at)
```

## Request flow (happy path)

```mermaid
sequenceDiagram
    participant C as Client
    participant A as API
    participant DB as Postgres

    C->>A: POST /reservations (Idempotency-Key)
    A->>DB: BEGIN; SELECT stock FOR UPDATE
    DB-->>A: available=5
    A->>DB: UPDATE stock; INSERT ledger pair; COMMIT
    A-->>C: 201 reservation RESERVED

    C->>A: POST /reservations/{id}/charge
    A->>DB: INSERT ledger pair (customer->in_flight); saga=CHARGED
    A-->>C: 200 CHARGED

    C->>A: POST /reservations/{id}/commit
    A->>DB: INSERT ledger pair (reserved->sold, in_flight->revenue); saga=COMMITTED
    A-->>C: 200 COMMITTED
```

## Failure flow

If `charge` fails (simulated payment decline), the API immediately issues the
compensating transaction: `reserved → warehouse` (release the stock), saga → 
`ROLLED_BACK`. No manual reconciliation step exists or is needed — the compensation is
part of the same request that discovered the failure.

## What "provably correct" means here, precisely

Not a formal proof — a testable guarantee: given the locking discipline in §3 and the
idempotency discipline in §4, (a) two concurrent reservations against the same SKU
cannot both succeed if their combined quantity exceeds `available`, and (b) no retried
request produces a second ledger entry. §6's property tests exercise this claim under
real concurrent load rather than asserting it only holds by inspection.
