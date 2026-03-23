"""
Tests for billing service (app/billing.py).

All Stripe API calls are mocked — no real network calls are made.
"""
import pytest
from unittest.mock import MagicMock, patch

from app.billing import (
    PLAN_LIMITS,
    cancel_subscription,
    create_checkout_session,
    create_customer,
    get_subscription,
    handle_webhook,
    is_within_limit,
    memory_limit_for_plan,
)


# ---------------------------------------------------------------------------
# memory_limit_for_plan
# ---------------------------------------------------------------------------

class TestMemoryLimitForPlan:
    def test_free_plan_returns_correct_limit(self):
        assert memory_limit_for_plan("free") == PLAN_LIMITS["free"]

    def test_pro_plan_returns_correct_limit(self):
        assert memory_limit_for_plan("pro") == PLAN_LIMITS["pro"]

    def test_unknown_plan_defaults_to_free_limit(self):
        assert memory_limit_for_plan("enterprise") == PLAN_LIMITS["free"]

    def test_free_limit_less_than_pro_limit(self):
        assert memory_limit_for_plan("free") < memory_limit_for_plan("pro")


# ---------------------------------------------------------------------------
# is_within_limit
# ---------------------------------------------------------------------------

class TestIsWithinLimit:
    def test_zero_is_within_free_limit(self):
        assert is_within_limit(0, "free") is True

    def test_one_below_limit_is_within(self):
        limit = memory_limit_for_plan("free")
        assert is_within_limit(limit - 1, "free") is True

    def test_at_limit_is_not_within(self):
        limit = memory_limit_for_plan("free")
        assert is_within_limit(limit, "free") is False

    def test_over_limit_is_not_within(self):
        limit = memory_limit_for_plan("free")
        assert is_within_limit(limit + 100, "free") is False

    def test_pro_plan_has_higher_limit(self):
        free_limit = memory_limit_for_plan("free")
        assert is_within_limit(free_limit, "pro") is True

    def test_unknown_plan_uses_free_limit(self):
        limit = memory_limit_for_plan("free")
        assert is_within_limit(limit, "unknown_plan") is False


# ---------------------------------------------------------------------------
# create_customer
# ---------------------------------------------------------------------------

class TestCreateCustomer:
    @patch("app.billing.stripe.Customer.create")
    def test_returns_customer_id(self, mock_create):
        mock_create.return_value = MagicMock(id="cus_test123")
        result = create_customer(agent_id="agent-uuid", email="test@example.com")
        assert result == "cus_test123"

    @patch("app.billing.stripe.Customer.create")
    def test_passes_correct_metadata(self, mock_create):
        mock_create.return_value = MagicMock(id="cus_abc")
        create_customer(agent_id="my-agent", email="foo@bar.com")
        mock_create.assert_called_once_with(
            email="foo@bar.com",
            metadata={"agent_id": "my-agent"},
        )


# ---------------------------------------------------------------------------
# create_checkout_session
# ---------------------------------------------------------------------------

class TestCreateCheckoutSession:
    @patch("app.billing.stripe.checkout.Session.create")
    def test_returns_session_url(self, mock_create):
        mock_create.return_value = MagicMock(url="https://checkout.stripe.com/pay/test")
        url = create_checkout_session(
            customer_id="cus_123",
            success_url="https://app.example.com/success",
            cancel_url="https://app.example.com/cancel",
        )
        assert url == "https://checkout.stripe.com/pay/test"

    @patch("app.billing.stripe.checkout.Session.create")
    def test_uses_subscription_mode(self, mock_create):
        mock_create.return_value = MagicMock(url="https://stripe.com")
        create_checkout_session("cus_x", "https://ok", "https://cancel")
        _, kwargs = mock_create.call_args
        assert kwargs.get("mode") == "subscription"


# ---------------------------------------------------------------------------
# cancel_subscription
# ---------------------------------------------------------------------------

class TestCancelSubscription:
    @patch("app.billing.stripe.Subscription.modify")
    def test_returns_dict(self, mock_modify):
        fake_sub = {"id": "sub_abc", "cancel_at_period_end": True}
        mock_modify.return_value = fake_sub
        result = cancel_subscription("sub_abc")
        assert isinstance(result, dict)

    @patch("app.billing.stripe.Subscription.modify")
    def test_passes_cancel_at_period_end(self, mock_modify):
        mock_modify.return_value = {}
        cancel_subscription("sub_xyz")
        mock_modify.assert_called_once_with("sub_xyz", cancel_at_period_end=True)


# ---------------------------------------------------------------------------
# get_subscription
# ---------------------------------------------------------------------------

class TestGetSubscription:
    @patch("app.billing.stripe.Subscription.retrieve")
    def test_returns_dict(self, mock_retrieve):
        mock_retrieve.return_value = {"id": "sub_abc", "status": "active"}
        result = get_subscription("sub_abc")
        assert isinstance(result, dict)
        assert result["status"] == "active"


# ---------------------------------------------------------------------------
# handle_webhook
# ---------------------------------------------------------------------------

class TestHandleWebhook:
    @patch("app.billing.stripe.Webhook.construct_event")
    def test_valid_webhook_returns_dict(self, mock_construct):
        mock_construct.return_value = {"type": "customer.subscription.updated", "data": {}}
        result = handle_webhook(b"payload", "sig_header")
        assert isinstance(result, dict)
        assert result["type"] == "customer.subscription.updated"

    @patch("app.billing.stripe.Webhook.construct_event")
    def test_invalid_signature_raises(self, mock_construct):
        import stripe as stripe_lib

        mock_construct.side_effect = stripe_lib.error.SignatureVerificationError(
            "Invalid", "sig"
        )
        with pytest.raises(stripe_lib.error.SignatureVerificationError):
            handle_webhook(b"bad", "bad_sig")
