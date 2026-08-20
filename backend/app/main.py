from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import Base, engine
from app.routers import stock, reservations, ledger, health, chaos

app = FastAPI(title="StockLedger")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stock.router)
app.include_router(reservations.router)
app.include_router(ledger.router)
app.include_router(health.router)
app.include_router(chaos.router)


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


@app.get("/")
def root():
    return {"service": "StockLedger", "status": "ok"}
