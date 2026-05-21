from fastapi import FastAPI, Depends, HTTPException, Request, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from contextlib import asynccontextmanager
import httpx
import os
import mercadopago
from typing import Optional, List
import uuid

from database import engine, Base, get_db
from models import Order as OrderModel, OrderItem as OrderItemModel
from schemas import CheckoutRequest, OrderResponse

PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://localhost:8001")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8005")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8004")
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "YOUR_MERCADOPAGO_ACCESS_TOKEN")
MIN_ORDER_AMOUNT = float(os.getenv("MIN_ORDER_AMOUNT", "5000"))
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(title="Order & Checkout Service", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/orders", response_model=List[OrderResponse])
async def list_orders(email: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    query = select(OrderModel).options(selectinload(OrderModel.items)).order_by(OrderModel.created_at.desc())
    if email:
        query = query.where(OrderModel.customer_email == email)
    result = await db.execute(query)
    return result.scalars().all()

@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(OrderModel).options(selectinload(OrderModel.items)).where(OrderModel.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    order_dict = {
        "id": order.id,
        "customer_email": order.customer_email,
        "status": order.status,
        "total_amount": order.total_amount,
        "created_at": order.created_at,
        "items": []
    }
    
    async with httpx.AsyncClient() as client:
        for item in order.items:
            product_name = f"Producto {item.product_id}"
            product_image = None
            try:
                resp = await client.get(f"{PRODUCT_SERVICE_URL}/products/{item.product_id}")
                if resp.status_code == 200:
                    product_data = resp.json()
                    product_name = product_data.get("name", product_name)
                    product_image = product_data.get("image_url", product_image)
            except Exception as e:
                print(f"Error fetching product {item.product_id}: {e}")
                
            order_dict["items"].append({
                "id": item.id,
                "product_id": item.product_id,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "product_name": product_name,
                "product_image": product_image
            })
            
    return order_dict

@app.post("/checkout/create_preference")
async def create_preference(request: CheckoutRequest, db: AsyncSession = Depends(get_db)):
    try:
        total_amount = 0.0
        order_items = []
        preference_items = []

        async with httpx.AsyncClient() as client:
            for item in request.items:
                resp = await client.get(f"{PRODUCT_SERVICE_URL}/products/{item.product_id}")
                if resp.status_code != 200:
                    raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
                
                product = resp.json()
                total_amount += product['price'] * item.quantity
                
                order_items.append(OrderItemModel(
                    product_id=product['id'],
                    quantity=item.quantity,
                    unit_price=product['price']
                ))
                
                preference_items.append({
                    "title": product['name'],
                    "quantity": item.quantity,
                    "unit_price": product['price'],
                    "id": str(product['id'])
                })

        if total_amount < MIN_ORDER_AMOUNT:
            raise HTTPException(status_code=400, detail=f"Minimum order amount is ${MIN_ORDER_AMOUNT}")

        order = OrderModel(
            customer_email=request.customer_email,
            status="pending",
            total_amount=total_amount,
            items=order_items
        )
        db.add(order)
        await db.commit()
        await db.refresh(order)

        preference_data = {
            "items": preference_items,
            "external_reference": str(order.id),
            "back_urls": {
                "success": "https://localhost:5173/checkout",
                "failure": "https://localhost:5173/checkout",
                "pending": "https://localhost:5173/checkout"
            },
            "auto_return": "approved",
            "statement_descriptor": "Zig Zag",
            "binary_mode": True
        }

        preference_response = sdk.preference().create(preference_data)
        print("MP preference response:", preference_response, flush=True)
        response_data = preference_response.get("response", {})
        if "id" not in response_data:
            raise HTTPException(status_code=500, detail=f"MercadoPago error: {preference_response}")
        return {"id": response_data["id"], "order_id": order.id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/checkout/webhook")
async def webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_signature: Optional[str] = Header(None, alias="x-signature"),
    x_request_id: Optional[str] = Header(None, alias="x-request-id"),
    data_id: Optional[str] = Query(None, alias="data.id"),
    type: Optional[str] = Query(None)
):
    payload = await request.json()
    notification_type = payload.get("type") or type
    
    if notification_type == "payment":
        payment_id = payload.get("data", {}).get("id") or data_id
        if payment_id:
            try:
                payment_info = sdk.payment().get(payment_id)
                payment_response = payment_info.get("response", {})
                status = payment_response.get("status")
                external_reference = payment_response.get("external_reference")
                
                if external_reference:
                    order_result = await db.execute(select(OrderModel).where(OrderModel.id == int(external_reference)))
                    order = order_result.scalar_one_or_none()
                    if order:
                        if status == "approved" and order.status != "paid":
                            order.status = "paid"
                            
                            # Trigger notifications
                            try:
                                async with httpx.AsyncClient() as client:
                                    # Fetch user data to get name and phone
                                    user_resp = await client.get(f"{AUTH_SERVICE_URL}/auth/users/{order.customer_email}")
                                    customer_name = order.customer_email
                                    customer_phone = ""
                                    if user_resp.status_code == 200:
                                        user_data = user_resp.json()
                                        customer_name = user_data.get("first_name", "") or order.customer_email
                                        customer_phone = user_data.get("phone", "")
                                        
                                    # Fetch product details for email
                                    items_for_email = []
                                    items_result = await db.execute(select(OrderItemModel).where(OrderItemModel.order_id == order.id))
                                    order_items = items_result.scalars().all()
                                    
                                    for item in order_items:
                                        product_name = f"Producto {item.product_id}"
                                        try:
                                            p_resp = await client.get(f"{PRODUCT_SERVICE_URL}/products/{item.product_id}")
                                            if p_resp.status_code == 200:
                                                product_name = p_resp.json().get("name", product_name)
                                        except:
                                            pass
                                            
                                        items_for_email.append({
                                            "product_name": product_name,
                                            "quantity": item.quantity,
                                            "unit_price": item.unit_price
                                        })
                                    
                                    # Send Email Ticket
                                    await client.post(f"{NOTIFICATION_SERVICE_URL}/notify/email", json={
                                        "to_email": order.customer_email,
                                        "customer_name": customer_name,
                                        "order_id": str(order.id),
                                        "items": items_for_email,
                                        "total_amount": order.total_amount
                                    })
                                    
                                    # Send WhatsApp update
                                    if customer_phone:
                                        await client.post(f"{NOTIFICATION_SERVICE_URL}/notify/whatsapp", json={
                                            "to_phone": customer_phone,
                                            "customer_name": customer_name,
                                            "order_id": str(order.id),
                                            "status": "paid"
                                        })
                            except Exception as e:
                                print("Error triggering notifications:", e)
                                
                        elif status in ["rejected", "cancelled"]:
                            order.status = "failed"
                        await db.commit()
            except Exception as e:
                print("Webhook error:", e)
                
    return {"status": "success"}

class OrderStatusUpdate(BaseModel):
    status: str

@app.put("/orders/{order_id}/status")
async def update_order_status(order_id: str, status_update: OrderStatusUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(OrderModel).where(OrderModel.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    order.status = status_update.status
    await db.commit()
    
    # Trigger WhatsApp Notification
    try:
        async with httpx.AsyncClient() as client:
            user_resp = await client.get(f"{AUTH_SERVICE_URL}/auth/users/{order.customer_email}")
            if user_resp.status_code == 200:
                user_data = user_resp.json()
                customer_name = user_data.get("first_name", "") or order.customer_email
                customer_phone = user_data.get("phone", "")
                
                if customer_phone:
                    await client.post(f"{NOTIFICATION_SERVICE_URL}/notify/whatsapp", json={
                        "to_phone": customer_phone,
                        "customer_name": customer_name,
                        "order_id": str(order.id),
                        "status": status_update.status
                    })
    except Exception as e:
        print("Error triggering whatsapp notification for status update:", e)
        
    return {"status": "success", "new_status": order.status}

@app.post("/checkout/process_payment")
async def process_payment(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        body = await request.json()

        payment_data = {
            "transaction_amount": float(body.get("transaction_amount")),
            "token": body.get("token"),
            "description": body.get("description", "ZigZag Groceries Order"),
            "installments": int(body.get("installments", 1)),
            "payment_method_id": body.get("payment_method_id"),
            "issuer_id": body.get("issuer_id"),
            "payer": {
                "email": body.get("payer", {}).get("email"),
                "identification": body.get("payer", {}).get("identification", {})
            }
        }

        # Idempotency key to prevent duplicate charges
        request_options = mercadopago.config.RequestOptions()
        request_options.custom_headers = {
            "x-idempotency-key": str(uuid.uuid4())
        }

        result = sdk.payment().create(payment_data, request_options)
        payment = result.get("response", {})
        status = payment.get("status")

        # Update order status if external_reference exists
        order_id = body.get("order_id")
        if order_id:
            order_result = await db.execute(
                select(OrderModel).where(OrderModel.id == int(order_id))
            )
            order = order_result.scalar_one_or_none()
            if order:
                if status == "approved":
                    order.status = "paid"
                elif status in ["rejected", "cancelled"]:
                    order.status = "failed"
                elif status == "in_process":
                    order.status = "pending"
                await db.commit()

        return {
            "status": status,
            "status_detail": payment.get("status_detail"),
            "id": payment.get("id"),
            "order_id": order_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
