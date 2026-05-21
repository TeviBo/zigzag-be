from pydantic import BaseModel
from typing import List, Optional

class CartItemCreate(BaseModel):
    product_id: int
    quantity: int

class CartItemResponse(BaseModel):
    id: int
    cart_id: str
    product_id: int
    quantity: int
    
    class Config:
        from_attributes = True

class CartResponse(BaseModel):
    id: str
    items: List[CartItemResponse] = []
    
    class Config:
        from_attributes = True
