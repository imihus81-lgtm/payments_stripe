import os, json, logging
from flask import Flask, request, render_template, jsonify, redirect, url_for
from flask_cors import CORS

# ---------- App ----------
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("app")

# ---------- Config ----------
STRIPE_SECRET_KEY   = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID     = os.getenv("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
PUBLIC_BASE_URL     = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")

# Import Stripe only if key present (avoids import crash on Render while building)
try:
    import stripe  # type: ignore
    if STRIPE_SECRET_KEY:
        stripe.api_key = STRIPE_SECRET_KEY
except Exception as e:
    log.warning("Stripe SDK not initialized yet: %s", e)

# ---------- Brain hook (optional) ----------
# Try to import your brain. If not present (Render), fall back to a safe no-op so the app still runs.
def _noop_record_purchase(email, niche, city):
    log.info("🧠(noop) record_purchase(email=%s, niche=%s, city=%s)", email, niche, city)

try:
    # expected path if you later add the brain into this repo:
    from ceo_brain.brain.api_hooks import record_purchase as _real_record_purchase  # type: ignore
    record_purchase = _real_record_purchase
    log.info("✅ Brain hook loaded.")
except Exception:
    record_purchase = _noop_record_purchase
    log.info("⚠️ Brain not found. Using no-op record_purchase.")

# ---------- Routes ----------
@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/")
def index():
    # Simple form lives in templates/index.html
    return render_template("index.html")

@app.get("/stripe-verify")
def stripe_verify():
    return render_template("verify.html", business="XAI Agent",
                           support="support@xaiagent.ai",
                           webhook_path="/stripe/webhook")

@app.get("/success")
def success():
    return render_template("success.html")

@app.post("/checkout")
def checkout():
    if not STRIPE_SECRET_KEY or not STRIPE_PRICE_ID:
        return jsonify({"error": "Stripe env vars missing"}), 400

    data = request.get_json(force=True)
    niche = (data.get("niche") or "").strip()
    city  = (data.get("city") or "").strip()

    # Create a Checkout Session
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
        success_url=f"{PUBLIC_BASE_URL}/success",
        cancel_url=f"{PUBLIC_BASE_URL}/",
        metadata={"niche": niche, "city": city},
    )
    return jsonify({"url": session.url})

@app.post("/stripe/webhook")
def stripe_webhook():
    payload = request.get_data(as_text=True)
    sig = request.headers.get("Stripe-Signature", "")
    if not STRIPE_WEBHOOK_SECRET:
        return "Missing webhook secret", 400

    try:
        event = stripe.Webhook.construct_event(
            payload, sig, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        log.exception("Webhook signature error: %s", e)
        return "bad sig", 400

    if event["type"] == "checkout.session.completed":
        obj = event["data"]["object"]
        email = (obj.get("customer_details") or {}).get("email") or ""
        niche = (obj.get("metadata") or {}).get("niche") or ""
        city  = (obj.get("metadata") or {}).get("city") or ""
        log.info("💳 Checkout completed: email=%s niche=%s city=%s", email, niche, city)
        # Call brain (no-op if brain not present):
        try:
            record_purchase(email=email, niche=niche, city=city)
        except Exception as e:
            log.exception("record_purchase failed: %s", e)

    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=True)
