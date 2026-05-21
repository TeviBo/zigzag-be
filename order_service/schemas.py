from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class Item(BaseModel):
    product_id: int
    quantity: int

class CheckoutRequest(BaseModel):
    customer_email: str
    items: List[Item]

class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    unit_price: float
    product_name: Optional[str] = None
    product_image: Optional[str] = None
    class Config:
        from_attributes = True

class OrderResponse(BaseModel):
    id: str
    customer_email: str
    status: str
    total_amount: float
    created_at: datetime
    items: List[OrderItemResponse] = []
    class Config:
        from_attributes = True
