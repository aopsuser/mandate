"""Policy engine tests — run with: python3 -m unittest discover -s tests"""

from __future__ import annotations

import time
import unittest

from mandate import policy


def mandate(**overrides):
    base = {
        "id": "mnd_test",
        "agent": "Scout",
        "currency": "USD",
        "budget": 300.0,
        "per_txn_cap": 150.0,
        "approval_threshold": 100.0,
        "merchants": ["stride.run"],
        "categories": ["footwear"],
        "max_purchases_per_hour": 12,
        "expires_at": time.time() + 3600,
        "status": "active",
    }
    base.update(overrides)
    return base


def offer(**overrides):
    base = {
        "id": "sku_1",
        "name": "Sprint Lite",
        "merchant": "stride.run",
        "merchant_name": "Stride Run Co.",
        "category": "footwear",
        "price": 74.0,
        "rating": 4.2,
    }
    base.update(overrides)
    return base


class PolicyTests(unittest.TestCase):
    def test_allow_inside_every_limit(self):
        decision = policy.evaluate(mandate=mandate(), offer=offer(), spent=0)
        self.assertEqual(decision.verdict, policy.ALLOW)
        self.assertIn("auto-approved", decision.reason)

    def test_approval_above_threshold(self):
        decision = policy.evaluate(
            mandate=mandate(), offer=offer(price=118.0), spent=0
        )
        self.assertEqual(decision.verdict, policy.APPROVAL)
        threshold = next(c for c in decision.checks if c.id == "approval")
        self.assertEqual(threshold.status, "warn")

    def test_block_when_merchant_not_allowlisted(self):
        decision = policy.evaluate(
            mandate=mandate(), offer=offer(merchant="sneakerhub.market"), spent=0
        )
        self.assertEqual(decision.verdict, policy.BLOCK)
        self.assertIn("sneakerhub.market", decision.reason)

    def test_block_when_category_not_authorized(self):
        decision = policy.evaluate(
            mandate=mandate(), offer=offer(category="wearables"), spent=0
        )
        self.assertEqual(decision.verdict, policy.BLOCK)

    def test_block_when_over_per_transaction_cap(self):
        decision = policy.evaluate(
            mandate=mandate(per_txn_cap=50.0, approval_threshold=0.0),
            offer=offer(price=74.0),
            spent=0,
        )
        self.assertEqual(decision.verdict, policy.BLOCK)
        self.assertIn("per-transaction cap", decision.reason)

    def test_block_when_budget_exhausted(self):
        decision = policy.evaluate(mandate=mandate(), offer=offer(price=74.0), spent=250.0)
        self.assertEqual(decision.verdict, policy.BLOCK)
        self.assertIn("over budget", decision.reason)

    def test_block_when_mandate_revoked(self):
        decision = policy.evaluate(
            mandate=mandate(status="revoked"), offer=offer(), spent=0
        )
        self.assertEqual(decision.verdict, policy.BLOCK)
        self.assertIn("Revoked", decision.reason)

    def test_block_when_expired(self):
        decision = policy.evaluate(
            mandate=mandate(expires_at=time.time() - 1), offer=offer(), spent=0
        )
        self.assertEqual(decision.verdict, policy.BLOCK)

    def test_block_when_velocity_limit_hit(self):
        decision = policy.evaluate(
            mandate=mandate(max_purchases_per_hour=2),
            offer=offer(),
            spent=0,
            purchases_last_hour=2,
        )
        self.assertEqual(decision.verdict, policy.BLOCK)

    def test_every_decision_returns_full_audit_trail(self):
        decision = policy.evaluate(mandate=mandate(), offer=offer(), spent=0)
        ids = {check.id for check in decision.checks}
        self.assertEqual(
            ids,
            {
                "status",
                "expiry",
                "merchant",
                "category",
                "cap",
                "budget",
                "velocity",
                "approval",
            },
        )

    def test_empty_allowlists_mean_any(self):
        decision = policy.evaluate(
            mandate=mandate(merchants=[], categories=[]),
            offer=offer(merchant="anything.example", category="wearables"),
            spent=0,
        )
        self.assertEqual(decision.verdict, policy.ALLOW)


if __name__ == "__main__":
    unittest.main()
