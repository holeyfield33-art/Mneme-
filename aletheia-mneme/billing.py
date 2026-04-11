import secrets
import stripe
import structlog
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
import env, auth, mailer as em
from db import get_db

stripe.api_key = env.STRIPE_SECRET_KEY
log = structlog.get_logger()
router = APIRouter()

@router.post("/billing/checkout")
async def checkout(request: Request, db=Depends(get_db)):
    body = await request.json()
    user_email = body.get("email", "")
    if not user_email or "@" not in user_email:
        raise HTTPException(400, "Valid email required")

    namespace_id = "ns_" + secrets.token_urlsafe(16)
    await db.execute(
        "INSERT INTO namespaces (id, email, tier) VALUES ($1,$2,'free')",
        namespace_id, user_email
    )
    raw_key, hashed = auth.generate_api_key("free")
    prefix = raw_key[:9]
    await db.execute(
        "INSERT INTO api_keys (namespace_id, key_hash, key_prefix) VALUES ($1,$2,$3)",
        namespace_id, hashed, prefix
    )

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{"price": env.STRIPE_PRICE_ID, "quantity": 1}],
        mode="subscription",
        customer_email=user_email,
        success_url="https://aletheia-mneme.onrender.com/billing/success",
        cancel_url="https://aletheia-mneme.onrender.com/pricing",
        metadata={"namespace_id": namespace_id}
    )

    em.send_free_key(user_email, raw_key)
    return JSONResponse({"checkout_url": session.url, "api_key": raw_key})

@router.post("/billing/webhook")
async def stripe_webhook(request: Request, db=Depends(get_db)):
    payload = await request.body()  # raw bytes — do NOT parse first
    sig = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(payload, sig, env.STRIPE_WEBHOOK_SECRET)
    except (stripe.error.SignatureVerificationError, ValueError):
        raise HTTPException(400, "Invalid signature")

    if await db.fetchrow("SELECT id FROM processed_events WHERE id=$1", event["id"]):
        return {"status": "already_handled"}

    try:
        if event["type"] == "checkout.session.completed":
            namespace_id = event["data"]["object"]["metadata"]["namespace_id"]
            customer_email = event["data"]["object"].get("customer_email", "")
            raw_key, hashed = auth.generate_api_key("premium")
            prefix = raw_key[:9]
            await db.execute(
                "UPDATE namespaces SET tier='premium' WHERE id=$1", namespace_id
            )
            await db.execute(
                "INSERT INTO api_keys (namespace_id, key_hash, key_prefix) VALUES ($1,$2,$3)",
                namespace_id, hashed, prefix
            )
            if customer_email:
                em.send_premium_upgrade(customer_email, raw_key)
            log.info("namespace_upgraded", namespace_id=namespace_id)

        elif event["type"] == "customer.subscription.deleted":
            namespace_id = event["data"]["object"]["metadata"].get("namespace_id", "")
            if namespace_id:
                await db.execute(
                    "UPDATE namespaces SET tier='free' WHERE id=$1", namespace_id
                )
                await db.execute(
                    "UPDATE api_keys SET revoked_at=NOW() WHERE namespace_id=$1 AND key_prefix LIKE 'mneme_p%'",
                    namespace_id
                )
                ns = await db.fetchrow("SELECT email FROM namespaces WHERE id=$1", namespace_id)
                if ns and ns["email"]:
                    em.send_downgrade(ns["email"])
    except Exception as e:
        log.error("webhook_processing_error", event_type=event["type"], error=str(e))

    await db.execute("INSERT INTO processed_events (id) VALUES ($1)", event["id"])
    return {"status": "success"}
