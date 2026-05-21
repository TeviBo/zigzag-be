from pydantic import BaseModel
from typing import List, Optional

class OrderItem(BaseModel):
    product_name: str
    quantity: int
    unit_price: float

class EmailRequest(BaseModel):
    to_email: str
    customer_name: str
    order_id: str
    items: List[OrderItem]
    total_amount: float

class WhatsappRequest(BaseModel):
    to_phone: str
    customer_name: str
    order_id: str
    status: str # 'paid', 'preparing', 'shipped', 'delivered'
