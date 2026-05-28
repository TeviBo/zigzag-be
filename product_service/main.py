from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import or_
from typing import List, Optional
from contextlib import asynccontextmanager

from database import engine, Base, get_db
from models import Product as ProductModel, Category as CategoryModel, Subcategory as SubcategoryModel
import schemas
import os
from auth import require_admin, CurrentUser

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(title="Product Service", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ──────────────────────────────────────────────
# Products
# ──────────────────────────────────────────────

@app.get("/products", response_model=List[schemas.Product])
async def read_products(
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
    subcategory_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    query = select(ProductModel).offset(skip).limit(limit)
    if category:
        query = query.where(ProductModel.category == category)
    if subcategory_id:
        query = query.where(ProductModel.subcategory_id == subcategory_id)
    result = await db.execute(query)
    return result.scalars().all()

@app.post("/products", response_model=schemas.Product)
async def create_product(
    product: schemas.ProductCreate,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    db_product = ProductModel(**product.model_dump())
    db.add(db_product)
    await db.commit()
    await db.refresh(db_product)
    return db_product

@app.get("/products/search", response_model=List[schemas.Product])
async def search_products(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    search_term = f"%{q}%"
    query = select(ProductModel).where(
        or_(
            ProductModel.name.ilike(search_term),
            ProductModel.description.ilike(search_term)
        )
    ).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()

@app.get("/products/{product_id}", response_model=schemas.Product)
async def read_product(product_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ProductModel).where(ProductModel.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

# ──────────────────────────────────────────────
# Categories
# ──────────────────────────────────────────────

@app.get("/categories", response_model=List[schemas.CategoryResponse])
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CategoryModel).options(selectinload(CategoryModel.subcategories)).order_by(CategoryModel.id)
    )
    return result.scalars().all()

@app.get("/categories/{slug}", response_model=schemas.CategoryDetail)
async def get_category(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CategoryModel)
        .options(
            selectinload(CategoryModel.subcategories).selectinload(SubcategoryModel.products)
        )
        .where(CategoryModel.slug == slug)
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category

# ──────────────────────────────────────────────
# Subcategories
# ──────────────────────────────────────────────

@app.get("/subcategories/{subcategory_id}", response_model=schemas.SubcategoryWithProducts)
async def get_subcategory(subcategory_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SubcategoryModel)
        .options(selectinload(SubcategoryModel.products))
        .where(SubcategoryModel.id == subcategory_id)
    )
    sub = result.scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="Subcategory not found")
    return sub
