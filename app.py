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
PUBLIC_BASE_URL       = os.getenv("PUBLIC_BASE_URL", "")  # e.g. https://pay.xaiagent.ai

# Optional: PayPal (for webhooks later if needed)
PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID", "")

# Validate ENV values for Stripe
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
    return {"service": "stripe-paypal-payment", "status": "ok"}, 200


# -----------------------------
#  HOME PAGE
# -----------------------------
@app.get("/")
def index():
    try:
        # index.html has Stripe + PayPal buttons
        return render_template("index.html")
    except TemplateNotFound:
        return """
        <h1>XAI Agent – Payments</h1>
        <p><b>index.html</b> missing in <b>/templates</b> folder.</p>
        """, 200


# -----------------------------
#  SUCCESS PAGE
# -----------------------------
@app.get("/success")
def success_page():
    """
    After successful payment (Stripe or PayPal) we redirect here.
    """
    try:
        return render_template("success.html")
    except TemplateNotFound:
        return """
        <h1>Payment Successful ✅</h1>
        <p><b>success.html</b> missing in <b>/templates</b> folder.</p>
        """, 200


# -----------------------------
#  CANCEL PAGE (optional)
# -----------------------------
@app.get("/cancel")
def cancel_page():
    try:
        return render_template("cancel.html")
    except TemplateNotFound:
        return """
        <h1>Payment Cancelled ❌</h1>
        <p><b>cancel.html</b> missing in <b>/templates</b> folder.</p>
        """, 200


# -----------------------------
#  STRIPE CHECKOUT – Create Session
# -----------------------------
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    """
    Creates a Stripe Checkout Session.
    The index.html "Pay with Card (Stripe)" button can just link to /checkout.
    """
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price": PRICE_ID,
                "quantity": 1
            }],
            success_url=f"{PUBLIC_BASE_URL}/success",
            cancel_url=f"{PUBLIC_BASE_URL}/cancel",
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
        print("❌ Stripe webhook signature error:", e)
        return "bad", 400

    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})
    print("✅ Stripe Event:", event_type)

    if event_type == "checkout.session.completed":
        print("💰 Stripe payment success")
        customer_email = data.get("customer_details", {}).get("email")
        amount_total = data.get("amount_total")
        print("Customer email:", customer_email)
        print("Amount (cents):", amount_total)

        # 👉 TODO: Deliver your product/service here
        # e.g. generate website/report, send email, log to DB, etc.

    return "ok", 200


# -----------------------------
#  PAYPAL WEBHOOK (Optional but Recommended)
# -----------------------------
@app.post("/paypal/webhook")
def paypal_webhook():
    """
    PayPal will POST events here (after you configure the webhook URL in PayPal dashboard).
    For now we just log the event.
    Later you can verify signatures and map it to orders/emails.
    """
    try:
        event = request.json or {}
    except Exception as e:
        print("❌ PayPal webhook JSON error:", e)
        return "bad", 400

    event_type = event.get("event_type")
    resource = event.get("resource", {})

    print("✅ PayPal Event:", event_type)

    # Common event when payment is fully captured
    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        amount = resource.get("amount", {}).get("value")
        currency = resource.get("amount", {}).get("currency_code")
        payer = resource.get("payer", {})
        payer_email = payer.get("email_address")
        print(f"💰 PayPal payment success: {amount} {currency} from {payer_email}")

        # 👉 TODO: Deliver your product/service here
        # same logic as Stripe: create website/report, send email, etc.

    return "ok", 200


# -----------------------------
#  MAIN (LOCAL RUN)
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
