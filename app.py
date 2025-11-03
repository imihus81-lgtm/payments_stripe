# payment/app.py
import os
import json
import logging
from datetime import datetime

from flask import Flask, request, jsonify, abort

# --- Stripe ---
import stripe

# --- PayPal ---
import base64
import requests

# =========================
# ENV & CONFIG
# =========================
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# PayPal: set PAYPAL_MODE to "sandbox" or "live"
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox").lower()
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID", "")

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

PAYPAL_API_BASE = "https://api-m.sandbox.paypal.com" if PAYPAL_MODE == "sandbox" else "https://api-m.paypal.com"

# =========================
# LOGGING
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("payment-app")

# =========================
# FLASK APP
# =========================
app = Flask(__name__)

@app.get("/")
def root():
    return jsonify({
        "status": "ok",
        "service": "payment",
        "time": datetime.utcnow().isoformat() + "Z"
    }), 200

@app.get("/healthz")
def healthz():
    return "ok", 200

# =========================
# STRIPE WEBHOOK
# =========================
@app.post("/stripe/webhook")
def stripe_webhook():
    if not STRIPE_WEBHOOK_SECRET:
        logger.error("Missing STRIPE_WEBHOOK_SECRET")
        return "Missing STRIPE_WEBHOOK_SECRET", 500

    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.exception("Invalid Stripe payload")
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError as e:
        logger.exception("Invalid Stripe signature")
        return "Invalid signature", 400

    etype = event.get("type")
    data = event.get("data", {}).get("object", {})
    logger.info(f"[Stripe] Event type: {etype}")

    try:
        if etype == "checkout.session.completed":
            # Payment succeeded for Checkout Sessions
            customer_email = data.get("customer_details", {}).get("email")
            amount_total = data.get("amount_total")
            currency = data.get("currency")
            logger.info(f"[Stripe] Checkout completed: {customer_email}, {amount_total} {currency}")
            # TODO: deliver product (generate ZIP, email download link, etc.)

        elif etype == "payment_intent.succeeded":
            amount = data.get("amount_received") or data.get("amount")
            currency = data.get("currency")
            logger.info(f"[Stripe] PaymentIntent succeeded: {amount} {currency}")
            # TODO: fulfill order

        elif etype == "invoice.payment_succeeded":
            logger.info(f"[Stripe] Invoice payment succeeded: {data.get('id')}")
            # TODO: provision/extend subscription

        else:
            logger.info(f"[Stripe] Unhandled event: {etype}")

        return "OK", 200
    except Exception:
        logger.exception("[Stripe] Error while handling event")
        return "Webhook handler error", 500

# =========================
# PAYPAL WEBHOOK
# =========================
def _paypal_get_access_token() -> str:
    """Get OAuth2 access token from PayPal."""
    auth = (PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET)
    headers = {"Accept": "application/json", "Accept-Language": "en_US"}
    data = {"grant_type": "client_credentials"}
    resp = requests.post(f"{PAYPAL_API_BASE}/v1/oauth2/token", headers=headers, data=data, auth=auth, timeout=20)
    resp.raise_for_status()
    return resp.json()["access_token"]

def _paypal_verify_signature(body: dict, headers: dict) -> bool:
    """
    Validate PayPal webhook using the /v1/notifications/verify-webhook-signature API.
    Docs: https://developer.paypal.com/docs/api/webhooks/v1/#verify-webhook-signature_post
    """
    if not (PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET and PAYPAL_WEBHOOK_ID):
        logger.error("Missing PayPal env vars (PAYPAL_CLIENT_ID/SECRET/WEBHOOK_ID)")
        return False

    try:
        access_token = _paypal_get_access_token()
    except Exception:
        logger.exception("Failed to obtain PayPal access token")
        return False

    verify_payload = {
        "transmission_id": headers.get("Paypal-Transmission-Id", ""),
        "transmission_time": headers.get("Paypal-Transmission-Time", ""),
        "cert_url": headers.get("Paypal-Cert-Url", ""),
        "auth_algo": headers.get("Paypal-Auth-Algo", ""),
        "transmission_sig": headers.get("Paypal-Transmission-Sig", ""),
        "webhook_id": PAYPAL_WEBHOOK_ID,  # from PayPal dashboard
        "webhook_event": body,
    }

    verify_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}",
    }

    try:
        resp = requests.post(
            f"{PAYPAL_API_BASE}/v1/notifications/verify-webhook-signature",
            headers=verify_headers,
            data=json.dumps(verify_payload),
            timeout=20
        )
        resp.raise_for_status()
        status = resp.json().get("verification_status")
        logger.info(f"[PayPal] verification_status={status}")
        return status == "SUCCESS"
    except Exception:
        logger.exception("PayPal signature verification call failed")
        return False

@app.post("/paypal/webhook")
def paypal_webhook():
    body = request.get_json(silent=True) or {}
    headers = request.headers

    if not _paypal_verify_signature(body, headers):
        return "Invalid PayPal signature", 400

    event_type = body.get("event_type", "")
    resource = body.get("resource", {})
    logger.info(f"[PayPal] Event: {event_type}")

    try:
        if event_type == "PAYMENT.CAPTURE.COMPLETED":
            amount = resource.get("amount", {}).get("value")
            currency = resource.get("amount", {}).get("currency_code")
            payer_email = (resource.get("payer", {}) or {}).get("email_address")
            logger.info(f"[PayPal] Payment completed: {amount} {currency} by {payer_email}")
            # TODO: deliver product

        elif event_type == "CHECKOUT.ORDER.APPROVED":
            order_id = resource.get("id")
            logger.info(f"[PayPal] Order approved: {order_id}")
            # (Optional) capture step if you use Orders API
            # TODO: capture & fulfill

        else:
            logger.info(f"[PayPal] Unhandled event: {event_type}")

        return "OK", 200
    except Exception:
        logger.exception("[PayPal] Error while handling event")
        return "Webhook handler error", 500

# =========================
# OPTIONAL: Success/Cancel redirect pages
# =========================
@app.get("/success")
def success():
    return "<h3>Payment successful. Thank you!</h3>", 200

@app.get("/cancel")
def cancel():
    return "<h3>Payment canceled.</h3>", 200

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    # bind to 0.0.0.0 for Render/Heroku/Docker
    app.run(host="0.0.0.0", port=port)
