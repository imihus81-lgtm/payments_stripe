import os
from flask import Flask, request, jsonify, render_template
import stripe

app = Flask(__name__, template_folder=".", static_folder=".")

# =====================
# ENV VARS
# =====================
STRIPE_SECRET_KEY     = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
PRICE_ID              = os.getenv("PRICE_ID", "")
PUBLIC_BASE_URL       = os.getenv("PUBLIC_BASE_URL", "")

stripe.api_key = STRIPE_SECRET_KEY


# =====================
# HEALTH CHECK
# =====================
@app.get("/healthz")
def healthz():
    return {"service":"stripe-payment","status":"ok"}, 200


# =====================
# HOME PAGE
# =====================
@app.get("/")
def index():
    return render_template("index.html")     # -> will show your form page


# =====================
# CHECKOUT START
# =====================
@app.post("/checkout")
def checkout():
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price": PRICE_ID,
                "quantity": 1,
            }],
            success_url=f"{PUBLIC_BASE_URL}/success.html",
            cancel_url=f"{PUBLIC_BASE_URL}/",
        )
        return jsonify({"url": session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =====================
# STRIPE WEBHOOK
# =====================
@app.post("/stripe/webhook")
def stripe_webhook():
    payload = request.data
    sig = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        print("❌ Webhook error:", e)
        return "bad", 400

    # log event
    print("✅ Stripe Event:", event.get("type"))

    return "ok", 200


# =====================
# MAIN LOCAL RUN
# =====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
