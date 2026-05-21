from fastapi import FastAPI, HTTPException
import os
import resend
from twilio.rest import Client
import schemas

app = FastAPI(title="Notification Service")

# Resend Config
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
resend.api_key = RESEND_API_KEY

# Twilio Config
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886") # Default Twilio Sandbox Number

twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

@app.post("/notify/email")
async def send_email_ticket(request: schemas.EmailRequest):
    if not RESEND_API_KEY:
        print(f"MOCK EMAIL: Envio de email simulado a {request.to_email} para orden {request.order_id}")
        return {"status": "mock_success"}

    items_html = ""
    for item in request.items:
        items_html += f"<li>{item.quantity}x {item.product_name} - ${item.unit_price:.2f}</li>"

    html_content = f"""
    <h1>¡Gracias por tu compra en ZigZag!</h1>
    <p>Hola {request.customer_name}, hemos recibido tu pedido <strong>#{request.order_id.split('-')[0]}</strong>.</p>
    <h3>Detalle de la compra:</h3>
    <ul>
        {items_html}
    </ul>
    <h2>Total: ${request.total_amount:.2f}</h2>
    <p>Te avisaremos por WhatsApp cuando haya novedades sobre tu envío.</p>
    """

    try:
        r = resend.Emails.send({
            "from": "ZigZag Tienda <onboarding@resend.dev>",
            "to": request.to_email,
            "subject": f"Tu ticket de compra #{request.order_id.split('-')[0]}",
            "html": html_content
        })
        return {"status": "success", "id": r.get('id')}
    except Exception as e:
        print("Resend Error:", e)
        raise HTTPException(status_code=500, detail=str(e))


STATUS_MESSAGES = {
    "paid": "✅ ¡Hola {name}! Hemos recibido tu pedido #{id} en ZigZag. Ya nos ponemos a prepararlo.",
    "preparing": "👨‍🍳 ¡Buenas noticias {name}! Tu pedido #{id} ya está en preparación.",
    "shipped": "🚚 ¡Atención {name}! Tu pedido #{id} ya está en camino a tu domicilio.",
    "delivered": "🎁 ¡Entregado! Tu pedido #{id} ya llegó a destino. ¡Que lo disfrutes {name}!"
}

@app.post("/notify/whatsapp")
async def send_whatsapp_update(request: schemas.WhatsappRequest):
    message_template = STATUS_MESSAGES.get(request.status)
    if not message_template:
        raise HTTPException(status_code=400, detail="Invalid status")

    short_id = request.order_id.split('-')[0]
    message_body = message_template.format(name=request.customer_name, id=short_id)

    if not twilio_client:
        print(f"MOCK WHATSAPP: Envio de WS simulado a {request.to_phone}: {message_body}")
        return {"status": "mock_success"}

    try:
        # Normalize phone number (ensure + prefix)
        to_phone = request.to_phone
        if not to_phone.startswith('+'):
            to_phone = '+' + to_phone

        message = twilio_client.messages.create(
            body=message_body,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=f"whatsapp:{to_phone}"
        )
        return {"status": "success", "sid": message.sid}
    except Exception as e:
        print("Twilio Error:", e)
        raise HTTPException(status_code=500, detail=str(e))
