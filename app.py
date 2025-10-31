import os
import sys
import json
import stripe
from flask import Flask, request, redirect, make_response, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

# Load .env if present (local dev)
load_dotenv()

# ---- Make ceo_brain package importable (sibling folder) ----
# automation_suite/
#   ├─ web_automation/
#   ├─ ceo_brain/
#   └─ payments_stripe/  <-- this app.py lives here
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../ceo_brain")))
from brain.api_hooks import record_purchase   # def record_purchase(email, niche="roofing contractor", city="Dallas")

# ---- Flask app ----
app = Flask(__name__)
CORS(app)

# ---- Stripe config ----
STRIPE_SECRET_KEY   = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PRICE_ID     = os.getenv("STRIPE_PRICE_ID", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
PUBLIC_BASE_URL     = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")

if not STRIPE_SECRET_KEY:
    print("[WARN] STRIPE_SECRET_KEY not set. Set it in your environment or .env")
if not STRIPE_PRICE_ID:
    print("[WARN] STRIPE_PRICE_ID not set. Set it in your environment or .env")

stripe.api_key = STRIPE_SECRET_KEY


# =========================
# Static verification files
# =========================
# Put verification files (e.g., stripe or apple pay) in:
#   payments_stripe/static/.well-known/your-file.txt
@app.get("/.well-known/<path:fname>")
def well_known(fname: str):
    folder = os.path.join(app.root_path, "static", ".well-known")
    return send_from_directory(folder, fname)


# =========
# Home page
# =========
# Minimal, template-free page with a form for niche/city and a "Buy" button.
@app.get("/")
def index():
    html = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>XAI Agent — Lead Pack</title>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; padding: 24px; max-width: 780px; margin: 0 auto; }}
    .card {{ border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px; box-shadow: 0 6px 18px rgba(0,0,0,0.06); }}
    label {{ display:block; margin-top:12px; font-weight:600; }}
    input, select {{ width:100%; padding:10px; border:1px solid #d1d5db; border-radius:8px; margin-top:6px; }}
    button {{ margin-top:18px; padding:12px 16px; background:#111827; color:#fff; border:none; border-radius:10px; cursor:pointer; font-weight:700; }}
    button:hover {{ background:#000; }}
    .muted {{ color:#6b7280; font-size:14px; }}
  </style>
</head>
<body>
  <h1>Buy a Lead Pack</h1>
  <p class="muted">Enter a niche and city, then pay securely with Stripe. After payment, we’ll generate your lead pack and email it to you automatically.</p>

  <div class="card">
    <form method="post" action="/create-checkout-session">
      <label>Niche</label>
      <input name="niche" placeholder="roofing contractor" value="roofing contractor" />

      <label>City</label>
      <input name="city" placeholder="Dallas" value="Dallas" />

      <!-- Hidden: your Stripe Price ID -->
      <input type="hidden" name="price_id" value="{STRIPE_PRICE_ID}"/>

      <button type="submit">Buy Now</button>
    </form>
    <p class="muted">Webhook: <code>/stripe/webhook</code> • Verify: <a href="/stripe-verify">/stripe-verify</a></p>
  </div>
</body>
</html>
"""
    return make_response(html, 200)


# ==========================
# Create checkout session
# ==========================
@app.post("/create-checkout-session")
def create_checkout_session():
    niche = request.form.get("niche") or "roofing contractor"
    city  = request.form.get("city") or "Dallas"
    price_id = request.form.get("price_id") or STRIPE_PRICE_ID

    if not STRIPE_SECRET_KEY or not price_id:
        return make_response({"error": "Stripe keys/price not configured."}, 400)

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{PUBLIC_BASE_URL}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{PUBLIC_BASE_URL}/cancel",
            # save the niche/city so webhook can trigger the correct job
            metadata={"niche": niche, "city": city, "price_id": price_id},
        )
        # Redirect the browser to Stripe-hosted checkout
        return redirect(session.url, code=303)
    except Exception as e:
        return make_response({"error": str(e)}, 400)


@app.get("/success")
def success():
    return "<h2>✅ Payment received. Your lead pack will be prepared and emailed shortly.</h2>"


@app.get("/cancel")
def cancel():
    return "<h2>❌ Payment canceled. You can try again anytime.</h2>"


# ==========================
# Stripe webhook endpoint
# ==========================
@app.post("/stripe/webhook")
def stripe_webhook():
    if not STRIPE_WEBHOOK_SECRET:
        return make_response({"error": "STRIPE_WEBHOOK_SECRET not set"}, 400)

    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        return make_response("Invalid signature", 400)
    except Exception as e:
        return make_response({"error": str(e)}, 400)

    # Only handle the event you need
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        # Buyer details
        customer_email = (session.get("customer_details") or {}).get("email", None)
        # Metadata set when creating session
        meta = session.get("metadata") or {}
        niche = meta.get("niche", "roofing contractor")
        city  = meta.get("city", "Dallas")

        print(f"✅ Stripe Payment Confirmed: {customer_email} | niche={niche} city={city}")

        # Trigger automation: CEO Brain → Web Automation → Email
        try:
            # This function should run the scraper and email the Excel to the buyer
            record_purchase(customer_email or "unknown@buyer.com", niche=niche, city=city)
        except Exception as e:
            # Never fail the webhook — log and keep 200 OK so Stripe doesn’t retry forever
            print("[ERROR] record_purchase failed:", e)

    return make_response("OK", 200)


# =============
# Verify page
# =============
@app.get("/stripe-verify")
def stripe_verify():
    html = """
    <h2>Stripe Verification</h2>
    <p>Business: XAI Agent</p>
    <p>Support: support@xaiagent.ai</p>
    <p>Webhook: <code>/stripe/webhook</code></p>
    """
    return make_response(html, 200)


if __name__ == "__main__":
    # Local dev server
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)
