from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
from contextlib import asynccontextmanager

from database import engine, Base, get_db
from models import Product as ProductModel
from schemas import Product, ProductCreate

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(title="Product Service", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/products", response_model=List[Product])
async def read_products(skip: int = 0, limit: int = 100, category: str = None, db: AsyncSession = Depends(get_db)):
    query = select(ProductModel).offset(skip).limit(limit)
    if category:
        query = query.where(ProductModel.category == category)
    result = await db.execute(query)
    return result.scalars().all()

@app.post("/products", response_model=Product)
async def create_product(product: ProductCreate, db: AsyncSession = Depends(get_db)):
    db_product = ProductModel(**product.model_dump())
    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)
    return db_product

@app.get("/products/{product_id}", response_model=Product)
async def read_product(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ProductModel).where(ProductModel.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product
