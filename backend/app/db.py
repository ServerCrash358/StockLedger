import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://stockledger:stockledger@localhost:5432/stockledger"
)

# Synchronous engine deliberately: the whole design relies on holding a row lock
# (SELECT ... FOR UPDATE) for the exact duration of one short transaction. A sync
# session per request thread makes that duration easy to reason about; pool_size
# controls how much real concurrency hits Postgres.
engine = create_engine(DATABASE_URL, pool_size=20, max_overflow=20, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
