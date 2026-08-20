import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://stockledger:stockledger@localhost:5432/stockledger_test"
)


@pytest.fixture(scope="session")
def engine():
    from app.db import Base
    eng = create_engine(TEST_DATABASE_URL, pool_size=30, max_overflow=30, future=True)
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@pytest.fixture(autouse=True)
def clean_tables(engine):
    yield
    with engine.begin() as conn:
        for table in (
            "idempotency_keys", "ledger_entries", "sagas", "stock_items",
            "accounts", "invariant_violations", "system_state",
        ):
            conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))


def make_sku(session_factory) -> str:
    sku = f"sku-{uuid.uuid4().hex[:8]}"
    return sku
