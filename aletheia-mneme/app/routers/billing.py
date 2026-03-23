"""
FastAPI router: billing (Stripe checkout, webhook, subscription status).
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

import stripe

from app import billing as billing_service
from app.database import get_db
from app.dependencies import get_current_agent
from app.models import Agent, Subscription
from app.schemas import CheckoutRequest, CheckoutResponse, SubscriptionOut

router = APIRouter(prefix="/billing", tags=["billing"])


def _get_or_create_subscription(db: Session, agent: Agent) -> Subscription:
    sub = agent.subscription
    if sub is None:
        sub = Subscription(agent_id=agent.id, stripe_customer_id="", plan="free")
        db.add(sub)
        db.commit()
        db.refresh(sub)
    return sub


@router.get("/subscription", response_model=SubscriptionOut)
def get_subscription_status(
    db: Session = Depends(get_db),
    agent: Agent = Depends(get_current_agent),
):
    sub = _get_or_create_subscription(db, agent)
    return sub


@router.post("/checkout", response_model=CheckoutResponse)
def create_checkout(
    body: CheckoutRequest,
    db: Session = Depends(get_db),
    agent: Agent = Depends(get_current_agent),
):
    """Create a Stripe Checkout session and return the redirect URL."""
    sub = _get_or_create_subscription(db, agent)

    if not sub.stripe_customer_id:
        customer_id = billing_service.create_customer(
            agent_id=str(agent.id),
            email=f"{agent.id}@mneme.local",
        )
        sub.stripe_customer_id = customer_id
        db.commit()

    url = billing_service.create_checkout_session(
        customer_id=sub.stripe_customer_id,
        success_url=body.success_url,
        cancel_url=body.cancel_url,
    )
    return CheckoutResponse(checkout_url=url)


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    db: Session = Depends(get_db),
):
    """Handle Stripe webhook events."""
    payload = await request.body()
    try:
        event = billing_service.handle_webhook(payload, stripe_signature)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe webhook signature",
        )

    event_type = event.get("type", "")

    if event_type == "customer.subscription.updated":
        _handle_subscription_updated(db, event["data"]["object"])
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(db, event["data"]["object"])

    return {"received": True}


def _handle_subscription_updated(db: Session, stripe_sub: dict) -> None:
    stripe_sub_id = stripe_sub["id"]
    sub = (
        db.query(Subscription)
        .filter(Subscription.stripe_subscription_id == stripe_sub_id)
        .first()
    )
    if sub:
        sub.status = stripe_sub.get("status", sub.status)
        db.commit()


def _handle_subscription_deleted(db: Session, stripe_sub: dict) -> None:
    stripe_sub_id = stripe_sub["id"]
    sub = (
        db.query(Subscription)
        .filter(Subscription.stripe_subscription_id == stripe_sub_id)
        .first()
    )
    if sub:
        sub.plan = "free"
        sub.status = "canceled"
        sub.stripe_subscription_id = None
        db.commit()
