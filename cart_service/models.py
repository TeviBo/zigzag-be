from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class Cart(Base):
    __tablename__ = "carts"
    id = Column(String, primary_key=True, index=True)
    items = relationship("CartItem", back_populates="cart", cascade="all, delete")

class CartItem(Base):
    __tablename__ = "cart_items"
    id = Column(Integer, primary_key=True, index=True)
    cart_id = Column(String, ForeignKey("carts.id"))
    product_id = Column(Integer)
    quantity = Column(Integer, default=1)
    cart = relationship("Cart", back_populates="items")

class Coupon(Base):
    __tablename__ = "coupons"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    discount_type = Column(String)  # 'percentage' or 'fixed'
    discount_value = Column(Integer) # if percentage, 1-100. If fixed, monetary amount.
    active = Column(Integer, default=1) # 1 for active, 0 for inactive
