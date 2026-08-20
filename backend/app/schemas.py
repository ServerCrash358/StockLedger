from pydantic import BaseModel


class StockItemOut(BaseModel):
    sku: str
    total: int
    available: int
    reserved: int

    class Config:
        from_attributes = True


class StockItemCreate(BaseModel):
    sku: str
    total: int


class ReservationCreate(BaseModel):
    sku: str
    qty: int
    customer_id: str
    amount_cents: int


class ChargeRequest(BaseModel):
    simulate_decline: bool = False


class SagaOut(BaseModel):
    id: str
    sku: str
    qty: int
    customer_id: str
    amount_cents: int
    state: str
    failure_reason: str | None = None

    class Config:
        from_attributes = True


class LedgerEntryOut(BaseModel):
    id: str
    transaction_id: str
    account_id: str
    direction: str
    amount: int
    sku: str | None
    created_at: str

    class Config:
        from_attributes = True


class HealthOut(BaseModel):
    halted: bool
    halted_reason: str | None = None
    last_checked: str | None = None
    ledger_balanced: bool
    stock_conserved: bool
