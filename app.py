import os
from datetime import datetime
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

PAYPAL_WEBHOOK_ID     = os.getenv("PAYPAL_WEBHOOK_ID", "")  # optional, for later verification

# Validate Stripe env
if not STRIPE_SECRET_KEY or not STRIPE_SECRET_KEY.startswith("sk_"):
    raise RuntimeError("❌ STRIPE_SECRET_KEY missing or invalid. Must be sk_...")

if not PRICE_ID or not PRICE_ID.startswith("price_"):
    raise RuntimeError("❌ PRICE_ID missing or invalid. Must be price_...")

if not PUBLIC_BASE_URL:
    raise RuntimeError("❌ PUBLIC_BASE_URL missing. Example: https://pay.xaiagent.ai")

stripe.api_key = STRIPE_SECRET_KEY


# -----------------------------
#  SMALL HELPER – RECORD ORDERS
# -----------------------------
def record_web_automation_order(source, email, amount, currency, transaction_id):
    """
    Common place to handle successful payments for Web Automation.
    For now we just log to console and to a local file.
    Later you can plug in:
      - website generator
      - email sending
      - database insert
    """
    timestamp = datetime.utcnow().isoformat()

    print("🔥 NEW WEB AUTOMATION ORDER")
    print("  Source       :", source)
    print("  Email        :", email)
    print("  Amount       :", amount, currency)
    print("  Transaction  :", transaction_id)
    print("  Time (UTC)   :", timestamp)

    # Log to a simple file (for manual fulfillment). On Render this is ephemeral,
    # but useful for local testing. For production use a DB (Supabase, etc.)
    try:
        with open("orders.log", "a", encoding="utf-8") as f:
            f.write(
                f"{timestamp}\t{source}\t{email}\t{amount} {currency}\t{transaction_id}\n"
            )
    except Exception as e:
        print("⚠️ Could not write to orders.log:", e)

    # TODO (later): call your web automation engine here
    # generate_website_for_customer(email, transaction_id)


# -----------------------------
#  HEALTH CHECK (Render)
# -----------------------------
@app.get("/healthz")
def healthz():
    return {"service": "web-automation-payments", "status": "ok"}, 200


# -----------------------------
#  HOME PAGE (Stripe + PayPal)
# -----------------------------
@app.get("/")
def index():
    try:
        return render_template("index.html")
    except TemplateNotFound:
        return """
        <h1>XAI Agent – Web Automation</h1>
        <p><b>index.html</b> missing in <b>/templates</b> folder.</p>
        """, 200


# -----------------------------
#  SUCCESS + CANCEL PAGES
# -----------------------------
@app.get("/success")
def success_page():
    try:
        return render_template("success.html")
    except TemplateNotFound:
        return "<h1>Payment Successful ✅</h1>", 200


@app.get("/cancel")
def cancel_page():
    try:
        return render_template("cancel.html")
    except TemplateNotFound:
        return "<h1>Payment Cancelled ❌</h1>", 200


# -----------------------------
#  STRIPE CHECKOUT – WEB AUTOMATION
# -----------------------------
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    """
    Creates a Stripe Checkout Session for the Web Automation product.
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
        return redirect(session.url, code=303)

    except Exception as e:
        print("❌ Error creating Stripe checkout:", e)
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
        customer_email = data.get("customer_details", {}).get("email")
        amount_total   = data.get("amount_total", 0) / 100.0  # convert from cents
        currency       = data.get("currency", "").upper()
        transaction_id = data.get("id")

        record_web_automation_order(
            source="stripe",
            email=customer_email,
            amount=amount_total,
            currency=currency,
            transaction_id=transaction_id,
        )

    return "ok", 200


# -----------------------------
#  PAYPAL WEBHOOK
# -----------------------------
@app.post("/paypal/webhook")
def paypal_webhook():
    """
    PayPal will POST events here.
    In dashboard you selected at least: Payment capture completed.
    """
    try:
        event = request.json or {}
    except Exception as e:
        print("❌ PayPal webhook JSON error:", e)
        return "bad", 400

    event_type = event.get("event_type")
    resource   = event.get("resource", {})

    print("✅ PayPal Event:", event_type)

    # When payment fully captured
    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        amount_obj    = resource.get("amount", {})
        amount_value  = float(amount_obj.get("value", "0"))
        currency_code = amount_obj.get("currency_code", "USD")

        payer        = resource.get("payer", {})
        payer_email  = payer.get("email_address")
        transaction_id = resource.get("id")

        record_web_automation_order(
            source="paypal",
            email=payer_email,
            amount=amount_value,
            currency=currency_code,
            transaction_id=transaction_id,
        )

    return "ok", 200


# -----------------------------
#  MAIN (LOCAL RUN)
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
