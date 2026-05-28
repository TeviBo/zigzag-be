import uuid
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import relationship
import datetime
from database import Base

class Order(Base):
    __tablename__ = "orders"
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    customer_email = Column(String, index=True)
    status = Column(String, default="pending")
    total_amount = Column(Float)
    coupon_code = Column(String, nullable=True)
    discount_amount = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    items = relationship("OrderItem", back_populates="order", cascade="all, delete")

class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String, ForeignKey("orders.id"))
    product_id = Column(Integer)
    quantity = Column(Integer, default=1)
    unit_price = Column(Float)
    order = relationship("Order", back_populates="items")
