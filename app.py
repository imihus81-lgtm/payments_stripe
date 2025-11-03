# payment/app.py

import os
from flask import Flask, request, jsonify
import stripe

# =====================
# ENV VARS
# =====================
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

stripe.api_key = STRIPE_SECRET_KEY

app = Flask(__name__)

# =====================
# BASIC ROUTES
# =====================

@app.get("/")
def root():
    return jsonify({"status":"ok","service":"stripe-payment"}), 200

@app.get("/healthz")
def healthz():
    return "ok", 200


# =====================
# STRIPE WEBHOOK
# =====================

@app.post("/stripe/webhook")
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        print("❌ Webhook signature error:", str(e))
        return "invalid", 400

    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})

    print(f"✅ Stripe Event: {event_type}")

    if event_type == "checkout.session.completed":
        customer_email = data.get("customer_details", {}).get("email")
        print(f"💰 CHECKOUT COMPLETE: {customer_email}")

        # TODO: call your web generator & deliver zip

    elif event_type == "payment_intent.succeeded":
        print("💚 Payment succeeded (PI)")
        # TODO: deliver

    return "ok", 200


# =====================
# MAIN (local only)
# =====================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
