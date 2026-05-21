from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from contextlib import asynccontextmanager
import httpx
import os

from database import engine, Base, get_db
from models import Cart as CartModel, CartItem as CartItemModel
from schemas import CartResponse, CartItemCreate

PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://localhost:8001")

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(title="Cart Service", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/cart/{session_id}", response_model=CartResponse)
async def get_cart(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CartModel).options(selectinload(CartModel.items)).where(CartModel.id == session_id))
    cart = result.scalar_one_or_none()
    if not cart:
        cart = CartModel(id=session_id)
        db.add(cart)
        await db.commit()
        await db.refresh(cart)
    return cart

@app.post("/cart/{session_id}/items", response_model=CartResponse)
async def add_cart_item(session_id: str, item: CartItemCreate, db: AsyncSession = Depends(get_db)):
    # Verify product exists via Product Service
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{PRODUCT_SERVICE_URL}/products/{item.product_id}")
        if resp.status_code != 200:
            raise HTTPException(status_code=404, detail="Product not found")

    cart_result = await db.execute(select(CartModel).where(CartModel.id == session_id))
    cart = cart_result.scalar_one_or_none()
    if not cart:
        cart = CartModel(id=session_id)
        db.add(cart)
        await db.commit()

    item_result = await db.execute(select(CartItemModel).where(CartItemModel.cart_id == session_id, CartItemModel.product_id == item.product_id))
    existing_item = item_result.scalar_one_or_none()
    
    if existing_item:
        existing_item.quantity += item.quantity
    else:
        new_item = CartItemModel(cart_id=session_id, product_id=item.product_id, quantity=item.quantity)
        db.add(new_item)
    await db.commit()
    
    updated_cart = await db.execute(select(CartModel).options(selectinload(CartModel.items)).where(CartModel.id == session_id))
    return updated_cart.scalar_one()

@app.delete("/cart/{session_id}/items/{item_id}", response_model=CartResponse)
async def remove_cart_item(session_id: str, item_id: int, db: AsyncSession = Depends(get_db)):
    item_result = await db.execute(select(CartItemModel).where(CartItemModel.id == item_id, CartItemModel.cart_id == session_id))
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Cart item not found")
    await db.delete(item)
    await db.commit()
    
    updated_cart = await db.execute(select(CartModel).options(selectinload(CartModel.items)).where(CartModel.id == session_id))
    return updated_cart.scalar_one()

@app.delete("/cart/{session_id}")
async def clear_cart(session_id: str, db: AsyncSession = Depends(get_db)):
    cart_result = await db.execute(select(CartModel).where(CartModel.id == session_id))
    cart = cart_result.scalar_one_or_none()
    if cart:
        await db.delete(cart)
        await db.commit()
    return {"status": "Cart cleared"}
