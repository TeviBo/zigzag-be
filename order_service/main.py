from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, Depends, HTTPException, Request, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from contextlib import asynccontextmanager
import hmac
import hashlib
import httpx
import os
import mercadopago
from typing import Optional, List
import uuid
from pydantic import BaseModel

from database import engine, Base, get_db
from models import Order as OrderModel, OrderItem as OrderItemModel
from schemas import CheckoutRequest, OrderResponse
from auth import CurrentUser, get_current_user, require_admin

PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://localhost:8001")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8005")
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost:8004")
CART_SERVICE_URL = os.getenv("CART_SERVICE_URL", "http://localhost:8002")
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN", "YOUR_MERCADOPAGO_ACCESS_TOKEN")
MP_WEBHOOK_SECRET = os.getenv("MP_WEBHOOK_SECRET", "")
INTERNAL_SERVICE_TOKEN = os.environ["INTERNAL_SERVICE_TOKEN"]
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
MIN_ORDER_AMOUNT = float(os.getenv("MIN_ORDER_AMOUNT", "5000"))
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="Order & Checkout Service", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/orders", response_model=List[OrderResponse])
async def list_orders(
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(OrderModel)
        .options(selectinload(OrderModel.items))
        .where(OrderModel.customer_email == current.email)
        .order_by(OrderModel.created_at.desc())
    )
    result = await db.execute(query)
    return result.scalars().all()


@app.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(OrderModel).options(selectinload(OrderModel.items)).where(OrderModel.id == order_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.customer_email != current.email and not current.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")

    order_dict = {
        "id": order.id,
        "customer_email": order.customer_email,
        "status": order.status,
        "total_amount": order.total_amount,
        "coupon_code": order.coupon_code,
        "discount_amount": order.discount_amount,
        "created_at": order.created_at,
        "items": [],
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
                "product_image": product_image,
            })

    return order_dict


@app.post("/checkout/create_preference")
async def create_preference(
    request: CheckoutRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        customer_email = current.email
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
                    unit_price=product['price'],
                ))

                preference_items.append({
                    "title": product['name'],
                    "quantity": item.quantity,
                    "unit_price": product['price'],
                    "id": str(product['id']),
                })

        if total_amount < MIN_ORDER_AMOUNT:
            raise HTTPException(status_code=400, detail=f"Minimum order amount is ${MIN_ORDER_AMOUNT}")

        discount_amount = 0.0
        applied_coupon = None

        if request.coupon_code:
            async with httpx.AsyncClient() as client:
                coupon_resp = await client.post(
                    f"{CART_SERVICE_URL}/coupons/validate",
                    json={"code": request.coupon_code},
                )
                if coupon_resp.status_code == 200:
                    coupon_data = coupon_resp.json()
                    applied_coupon = request.coupon_code
                    if coupon_data["discount_type"] == "percentage":
                        discount_amount = total_amount * (coupon_data["discount_value"] / 100.0)
                    elif coupon_data["discount_type"] == "fixed":
                        discount_amount = float(coupon_data["discount_value"])
                else:
                    print(f"Coupon validation failed: {coupon_resp.text}")

        pm_discount_amount = 0.0
        if request.payment_method == "mp_debit":
            pm_discount_amount = total_amount * 0.15
            discount_amount += pm_discount_amount

        final_amount = max(0, total_amount - discount_amount)

        if request.coupon_code and discount_amount - pm_discount_amount > 0:
            preference_items.append({
                "title": f"Descuento ({applied_coupon})",
                "quantity": 1,
                "unit_price": -(discount_amount - pm_discount_amount),
                "id": "discount",
            })

        if pm_discount_amount > 0:
            preference_items.append({
                "title": "Descuento 15% (Débito/Dinero en cuenta)",
                "quantity": 1,
                "unit_price": -pm_discount_amount,
                "id": "pm_discount",
            })

        order = OrderModel(
            customer_email=customer_email,
            status="pending",
            total_amount=final_amount,
            coupon_code=applied_coupon,
            discount_amount=discount_amount,
            items=order_items,
        )
        db.add(order)
        await db.commit()
        await db.refresh(order)

        preference_data = {
            "items": preference_items,
            "external_reference": str(order.id),
            "back_urls": {
                "success": f"{FRONTEND_URL}/checkout",
                "failure": f"{FRONTEND_URL}/checkout",
                "pending": f"{FRONTEND_URL}/checkout",
            },
            "auto_return": "approved",
            "statement_descriptor": "Zig Zag",
            "binary_mode": True,
        }

        if request.payment_method == "mp_debit":
            preference_data["payment_methods"] = {
                "excluded_payment_types": [
                    {"id": "credit_card"},
                    {"id": "ticket"},
                    {"id": "atm"},
                ]
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
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/checkout/create_order")
async def create_order(
    request: CheckoutRequest,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        customer_email = current.email
        total_amount = 0.0
        order_items = []

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
                    unit_price=product['price'],
                ))

        discount_amount = 0.0
        applied_coupon = None

        if request.coupon_code:
            async with httpx.AsyncClient() as client:
                coupon_resp = await client.post(
                    f"{CART_SERVICE_URL}/coupons/validate",
                    json={"code": request.coupon_code},
                )
                if coupon_resp.status_code == 200:
                    coupon_data = coupon_resp.json()
                    applied_coupon = request.coupon_code
                    if coupon_data["discount_type"] == "percentage":
                        discount_amount = total_amount * (coupon_data["discount_value"] / 100.0)
                    elif coupon_data["discount_type"] == "fixed":
                        discount_amount = float(coupon_data["discount_value"])

        pm_discount_amount = 0.0
        if request.payment_method == "cash":
            pm_discount_amount = total_amount * 0.15
            discount_amount += pm_discount_amount

        final_amount = max(0, total_amount - discount_amount)

        if final_amount < MIN_ORDER_AMOUNT:
            raise HTTPException(status_code=400, detail=f"Minimum order amount is ${MIN_ORDER_AMOUNT}")

        order = OrderModel(
            customer_email=customer_email,
            status="pending",
            total_amount=final_amount,
            coupon_code=applied_coupon,
            discount_amount=discount_amount,
            items=order_items,
        )
        db.add(order)
        await db.commit()
        await db.refresh(order)

        return {"order_id": order.id, "total": final_amount}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def verify_mp_signature(x_signature: str, x_request_id: str, data_id: str) -> bool:
    """
    MercadoPago webhook signature verification.
    Docs: https://www.mercadopago.com.ar/developers/en/docs/your-integrations/notifications/webhooks
    Format of x-signature: "ts=<timestamp>,v1=<hash>"
    Manifest: id:<data_id>;request-id:<x-request-id>;ts:<timestamp>;
    """
    if not MP_WEBHOOK_SECRET or not x_signature or not x_request_id or not data_id:
        return False
    try:
        parts = dict(p.strip().split("=", 1) for p in x_signature.split(",") if "=" in p)
        ts = parts.get("ts")
        received_hash = parts.get("v1")
        if not ts or not received_hash:
            return False
        manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
        computed = hmac.new(
            MP_WEBHOOK_SECRET.encode("utf-8"),
            manifest.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(computed, received_hash)
    except Exception as e:
        print("Signature verification error:", e)
        return False


@app.post("/checkout/webhook")
async def webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_signature: Optional[str] = Header(None, alias="x-signature"),
    x_request_id: Optional[str] = Header(None, alias="x-request-id"),
    data_id: Optional[str] = Query(None, alias="data.id"),
    type: Optional[str] = Query(None),
):
    payload = await request.json()
    notification_type = payload.get("type") or type
    payment_id = payload.get("data", {}).get("id") or data_id

    if not verify_mp_signature(x_signature or "", x_request_id or "", str(payment_id or "")):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if notification_type == "payment" and payment_id:
        try:
            payment_info = sdk.payment().get(payment_id)
            payment_response = payment_info.get("response", {})
            status = payment_response.get("status")
            external_reference = payment_response.get("external_reference")

            if external_reference:
                order_result = await db.execute(
                    select(OrderModel).where(OrderModel.id == int(external_reference))
                )
                order = order_result.scalar_one_or_none()
                if order:
                    if status == "approved" and order.status != "paid":
                        order.status = "paid"

                        try:
                            async with httpx.AsyncClient() as client:
                                user_resp = await client.get(
                                    f"{AUTH_SERVICE_URL}/auth/users/{order.customer_email}",
                                    headers={"X-Internal-Token": INTERNAL_SERVICE_TOKEN},
                                )
                                customer_name = order.customer_email
                                customer_phone = ""
                                if user_resp.status_code == 200:
                                    user_data = user_resp.json()
                                    customer_name = user_data.get("first_name", "") or order.customer_email
                                    customer_phone = user_data.get("phone", "")

                                items_for_email = []
                                items_result = await db.execute(
                                    select(OrderItemModel).where(OrderItemModel.order_id == order.id)
                                )
                                order_items = items_result.scalars().all()

                                for item in order_items:
                                    product_name = f"Producto {item.product_id}"
                                    try:
                                        p_resp = await client.get(
                                            f"{PRODUCT_SERVICE_URL}/products/{item.product_id}"
                                        )
                                        if p_resp.status_code == 200:
                                            product_name = p_resp.json().get("name", product_name)
                                    except:
                                        pass

                                    items_for_email.append({
                                        "product_name": product_name,
                                        "quantity": item.quantity,
                                        "unit_price": item.unit_price,
                                    })

                                await client.post(
                                    f"{NOTIFICATION_SERVICE_URL}/notify/email",
                                    headers={"X-Internal-Token": INTERNAL_SERVICE_TOKEN},
                                    json={
                                        "to_email": order.customer_email,
                                        "customer_name": customer_name,
                                        "order_id": str(order.id),
                                        "items": items_for_email,
                                        "total_amount": order.total_amount,
                                    },
                                )

                                if customer_phone:
                                    await client.post(
                                        f"{NOTIFICATION_SERVICE_URL}/notify/whatsapp",
                                        headers={"X-Internal-Token": INTERNAL_SERVICE_TOKEN},
                                        json={
                                            "to_phone": customer_phone,
                                            "customer_name": customer_name,
                                            "order_id": str(order.id),
                                            "status": "paid",
                                        },
                                    )
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
async def update_order_status(
    order_id: str,
    status_update: OrderStatusUpdate,
    _admin: CurrentUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(OrderModel).where(OrderModel.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = status_update.status
    await db.commit()

    try:
        async with httpx.AsyncClient() as client:
            user_resp = await client.get(
                f"{AUTH_SERVICE_URL}/auth/users/{order.customer_email}",
                headers={"X-Internal-Token": INTERNAL_SERVICE_TOKEN},
            )
            if user_resp.status_code == 200:
                user_data = user_resp.json()
                customer_name = user_data.get("first_name", "") or order.customer_email
                customer_phone = user_data.get("phone", "")

                if customer_phone:
                    await client.post(
                        f"{NOTIFICATION_SERVICE_URL}/notify/whatsapp",
                        headers={"X-Internal-Token": INTERNAL_SERVICE_TOKEN},
                        json={
                            "to_phone": customer_phone,
                            "customer_name": customer_name,
                            "order_id": str(order.id),
                            "status": status_update.status,
                        },
                    )
    except Exception as e:
        print("Error triggering whatsapp notification for status update:", e)

    return {"status": "success", "new_status": order.status}


@app.post("/checkout/process_payment")
async def process_payment(
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
                "email": current.email,
                "identification": body.get("payer", {}).get("identification", {}),
            },
        }

        request_options = mercadopago.config.RequestOptions()
        request_options.custom_headers = {
            "x-idempotency-key": str(uuid.uuid4())
        }

        result = sdk.payment().create(payment_data, request_options)
        payment = result.get("response", {})
        status = payment.get("status")

        order_id = body.get("order_id")
        if order_id:
            order_result = await db.execute(
                select(OrderModel).where(OrderModel.id == int(order_id))
            )
            order = order_result.scalar_one_or_none()
            if order:
                if order.customer_email != current.email:
                    raise HTTPException(status_code=403, detail="Forbidden")
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
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
