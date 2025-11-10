import os
from flask import Flask, request, jsonify, render_template
from jinja2 import TemplateNotFound
import stripe

# Flask finds HTML in ./templates
app = Flask(__name__, template_folder="templates")

# ======================
# ENV (trim & validate)
# ======================
STRIPE_SECRET_KEY     = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
PRICE_ID              = os.getenv("PRICE_ID", "").strip()
PUBLIC_BASE_URL       = os.getenv("PUBLIC_BASE_URL", "").strip()

if not STRIPE_SECRET_KEY:
    raise RuntimeError("STRIPE_SECRET_KEY is missing. Use your sk_test_... (or sk_live_...) key.")
if STRIPE_SECRET_KEY.startswith("pk_"):
    raise RuntimeError("You set a publishable key (pk_...). Set STRIPE_SECRET_KEY to your SECRET key (sk_...).")
if not PRICE_ID:
    raise RuntimeError("PRICE_ID is missing. Set it to your Stripe price_... id.")
if not PUBLIC_BASE_URL:
    raise RuntimeError("PUBLIC_BASE_URL is missing. Example: https://pay.xaiagent.ai (or http://127.0.0.1:10000 locally).")

stripe.api_key = STRIPE_SECRET_KEY

# ======================
# Health
# ======================
@app.get("/healthz")
def healthz():
    return {"service": "stripe-payment", "status": "ok"}, 200

# ======================
# Pages
# ======================
@app.get("/")
def index():
    try:
        return render_template("index.html")
    except TemplateNotFound:
        return (
            "<h1>Stripe Payment App</h1>"
            "<p>Missing <code>templates/index.html</code>.</p>",
            200,
        )

# Optional: serve these directly if you link to /success.html or /verify.html
@app.get("/success.html")
def success_page():
    try:
        return render_template("success.html")
    except TemplateNotFound:
        return "<h1>Success</h1><p>Add templates/success.html</p>", 200

@app.get("/verify.html")
def verify_page():
    try:
        return render_template("verify.html")
    except TemplateNotFound:
        return "<h1>Verify</h1><p>Add templates/verify.html</p>", 200

# ======================
# Checkout
# ======================
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
        # Bubble useful error back to logs/response
        return jsonify({"error": str(e)}), 500

# ======================
# Webhook
# ======================
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
    # You can branch here on event["type"] if needed

    return "ok", 200

# ======================
# Main (local)
# ======================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
