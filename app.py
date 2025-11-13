import os
from flask import Flask, request, jsonify, render_template, redirect
from jinja2 import TemplateNotFound
import stripe

# -----------------------------
#  FLASK SETUP
# -----------------------------
app = Flask(__name__, template_folder="templates")

# -----------------------------
#  ENVIRONMENT VARIABLES
# -----------------------------
STRIPE_SECRET_KEY     = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
PRICE_ID              = os.getenv("PRICE_ID", "")
PUBLIC_BASE_URL       = os.getenv("PUBLIC_BASE_URL", "")

# Validate ENV values
if not STRIPE_SECRET_KEY or not STRIPE_SECRET_KEY.startswith("sk_"):
    raise RuntimeError("❌ STRIPE_SECRET_KEY missing or invalid. Must be sk_...")

if not PRICE_ID or not PRICE_ID.startswith("price_"):
    raise RuntimeError("❌ PRICE_ID missing or invalid. Must be price_...")

if not PUBLIC_BASE_URL:
    raise RuntimeError("❌ PUBLIC_BASE_URL missing. Example: https://pay.xaiagent.ai")

stripe.api_key = STRIPE_SECRET_KEY


# -----------------------------
#  HEALTH CHECK (Render will use this)
# -----------------------------
@app.get("/healthz")
def healthz():
    return {"service": "stripe-payment", "status": "ok"}, 200


# -----------------------------
#  HOME PAGE
# -----------------------------
@app.get("/")
def index():
    try:
        return render_template("index.html")
    except TemplateNotFound:
        return """
        <h1>XAI Agent – Stripe Payment</h1>
        <p><b>index.html</b> missing in <b>/templates</b> folder.</p>
        """, 200


# -----------------------------
#  SUCCESS PAGE
# -----------------------------
@app.get("/success")
def success_page():
    """
    Stripe will redirect here after successful payment.
    """
    try:
        return render_template("success.html")
    except TemplateNotFound:
        return """
        <h1>Payment Successful ✅</h1>
        <p><b>success.html</b> missing in <b>/templates</b> folder.</p>
        """, 200


# -----------------------------
#  CHECKOUT – Create Stripe Session
# -----------------------------
@app.post("/checkout")
def checkout():
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price": PRICE_ID,
                "quantity": 1
            }],
            # ✅ IMPORTANT: route is /success, not success.html
            success_url=f"{PUBLIC_BASE_URL}/success",
            cancel_url=f"{PUBLIC_BASE_URL}/",
        )

        # Redirect user to Stripe Checkout
        return redirect(session.url, code=303)

    except Exception as e:
        print("❌ Error creating checkout:", e)
        return jsonify({"error": str(e)}), 500


# -----------------------------
#  STRIPE WEBHOOK
# -----------------------------
@app.post("/stripe/webhook")
def stripe_webhook():
    payload = request.data
    sig = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        print("❌ Webhook signature error:", e)
        return "bad", 400

    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})
    print("✅ Stripe Event:", event_type)

    if event_type == "checkout.session.completed":
        print("💰 Payment Success!")
        print("Customer email:", data.get("customer_details", {}).get("email"))

        # 👉 TODO LATER: after payment — trigger your:
        # - web automation engine
        # - domain setup
        # - lead delivery
        # - Gmail system
        # - CEO brain log entry

    return "ok", 200


# -----------------------------
#  MAIN (LOCAL RUN)
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
