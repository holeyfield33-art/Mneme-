"""
Billing service — thin wrapper around the Stripe API.

Plans
-----
free  : up to 500 stored memories, no semantic search
pro   : up to 10,000 stored memories + full semantic search
"""
import stripe

from app.config import get_settings

settings = get_settings()

# Initialise the Stripe client when this module is imported.
stripe.api_key = settings.stripe_secret_key

PLAN_LIMITS = {
    "free": 500,
    "pro": 10_000,
}


def create_customer(agent_id: str, email: str) -> str:
    """
    Create a Stripe customer and return their *customer_id*.

    Parameters
    ----------
    agent_id:
        The UUID of the agent (stored as Stripe metadata).
    email:
        Contact e-mail for the Stripe customer record.
    """
    customer = stripe.Customer.create(
        email=email,
        metadata={"agent_id": agent_id},
    )
    return customer.id


def create_checkout_session(customer_id: str, success_url: str, cancel_url: str) -> str:
    """
    Create a Stripe Checkout Session for the *pro* plan.

    Returns the URL the user should be redirected to.
    """
    session = stripe.checkout.Session.create(
        customer=customer_id,
        payment_method_types=["card"],
        line_items=[{"price": settings.stripe_price_id_pro, "quantity": 1}],
        mode="subscription",
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return session.url


def cancel_subscription(stripe_subscription_id: str) -> dict:
    """
    Cancel a Stripe subscription at the end of the current period.

    Returns the updated Stripe subscription object as a dict.
    """
    updated = stripe.Subscription.modify(
        stripe_subscription_id,
        cancel_at_period_end=True,
    )
    return dict(updated)


def get_subscription(stripe_subscription_id: str) -> dict:
    """Retrieve a Stripe subscription and return it as a dict."""
    sub = stripe.Subscription.retrieve(stripe_subscription_id)
    return dict(sub)


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """
    Validate and parse an incoming Stripe webhook.

    Returns the parsed event as a dict on success, raises
    ``stripe.error.SignatureVerificationError`` on failure.
    """
    event = stripe.Webhook.construct_event(
        payload, sig_header, settings.stripe_webhook_secret
    )
    return dict(event)


def memory_limit_for_plan(plan: str) -> int:
    """Return the maximum number of memories allowed for *plan*."""
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


def is_within_limit(current_count: int, plan: str) -> bool:
    """Return True when *current_count* is below the plan's memory limit."""
    return current_count < memory_limit_for_plan(plan)
