from pydantic import BaseModel
from typing import Optional, List

# --- Product ---
class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    image_url: Optional[str] = None
    category: Optional[str] = None
    subcategory_id: Optional[int] = None

class ProductCreate(ProductBase):
    pass

class Product(ProductBase):
    id: int
    class Config:
        from_attributes = True

# --- Subcategory ---
class SubcategoryBase(BaseModel):
    name: str
    slug: str
    category_id: int

class SubcategoryResponse(SubcategoryBase):
    id: int
    class Config:
        from_attributes = True

class SubcategoryWithProducts(SubcategoryResponse):
    products: List[Product] = []

# --- Category ---
class CategoryBase(BaseModel):
    name: str
    slug: str
    emoji: Optional[str] = None
    subtitle: Optional[str] = None

class CategoryResponse(CategoryBase):
    id: int
    subcategories: List[SubcategoryResponse] = []
    class Config:
        from_attributes = True

class CategoryDetail(CategoryBase):
    id: int
    subcategories: List[SubcategoryWithProducts] = []
    class Config:
        from_attributes = True
