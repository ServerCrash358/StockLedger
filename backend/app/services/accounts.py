from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import Account, AccountKind


def get_or_create_account(db: Session, name: str, kind: AccountKind) -> Account:
    """Concurrent-safe get-or-create. A plain "SELECT, then INSERT if missing"
    races: two transactions can both see no row and both INSERT, one losing to
    a UniqueViolation on `name`. INSERT ... ON CONFLICT DO NOTHING makes the
    creation itself atomic instead of relying on a prior read."""
    stmt = (
        pg_insert(Account)
        .values(name=name, kind=kind)
        .on_conflict_do_nothing(index_elements=[Account.name])
    )
    db.execute(stmt)
    return db.query(Account).filter(Account.name == name).one()


def warehouse_account(db: Session, sku: str) -> Account:
    return get_or_create_account(db, f"warehouse:{sku}", AccountKind.STOCK)


def reserved_account(db: Session, sku: str) -> Account:
    return get_or_create_account(db, f"reserved:{sku}", AccountKind.STOCK)


def sold_account(db: Session, sku: str) -> Account:
    return get_or_create_account(db, f"sold:{sku}", AccountKind.STOCK)


def customer_account(db: Session, customer_id: str) -> Account:
    return get_or_create_account(db, f"customer:{customer_id}", AccountKind.MONEY)


def in_flight_account(db: Session) -> Account:
    return get_or_create_account(db, "payments_in_flight", AccountKind.MONEY)


def revenue_account(db: Session) -> Account:
    return get_or_create_account(db, "revenue", AccountKind.MONEY)
