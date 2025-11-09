import os
from flask import Flask, request, jsonify, render_template
from jinja2 import TemplateNotFound
import stripe

app = Flask(__name__, template_folder="templates")

# ---- ENV ----
STRIPE_SECRET_KEY     = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
PRICE_ID              = os.getenv("PRICE_ID", "")
PUBLIC_BASE_URL       = os.getenv("PUBLIC_BASE_URL", "")

stripe.api_key = STRIPE_SECRET_KEY

# ---- Health ----
@app.get("/healthz")
def healthz():
    return {"service": "stripe-payment", "status": "ok"}, 200

# ---- Home ----
@app.get("/")
def index():
    try:
        return render_template("index.html")
    except TemplateNotFound:
        # Safe fallback so you’re never blocked by templates
        return """
        <h1>Stripe Payment App</h1>
        <p>Template <code>index.html</code> not found in <code>templates/</code>.</p>
        """, 200

# ---- Checkout ----
@app.post("/checkout")
def checkout():
    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": PRICE_ID, "quantity": 1}],
            success_url=f"{PUBLIC_BASE_URL}/success.html",
            cancel_url=f"{PUBLIC_BASE_URL}/",
        )
        return jsonify({"url": session.url})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ---- Webhook ----
@app.post("/stripe/webhook")
def stripe_webhook():
    payload = request.data
    sig = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        print("❌ Webhook error:", e)
        return "bad", 400

    print("✅ Stripe Event:", event.get("type"))
    return "ok", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
