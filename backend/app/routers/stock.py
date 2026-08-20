from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import StockItem
from app.schemas import StockItemOut, StockItemCreate

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("", response_model=list[StockItemOut])
def list_stock(db: Session = Depends(get_db)):
    return db.execute(select(StockItem)).scalars().all()


@router.post("", response_model=StockItemOut, status_code=201)
def create_stock(body: StockItemCreate, db: Session = Depends(get_db)):
    if db.get(StockItem, body.sku) is not None:
        raise HTTPException(status_code=409, detail="SKU already exists")
    item = StockItem(sku=body.sku, total=body.total, available=body.total, reserved=0)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/{sku}", response_model=StockItemOut)
def get_stock(sku: str, db: Session = Depends(get_db)):
    item = db.get(StockItem, sku)
    if item is None:
        raise HTTPException(status_code=404, detail="unknown SKU")
    return item
