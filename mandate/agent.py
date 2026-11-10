"""The agent loop.

Scout is deliberately simple: plan, search, rank, then try to pay. The
interesting part is not the shopping — it is that every spend attempt is
checked against a signed mandate, and the agent can only proceed by asking
a human when it wants to cross the approval threshold.
"""

from __future__ import annotations

import time
from typing import Any

from . import ai, catalog, crypto, policy
from .config import Settings
from .paypal import PayPalClient
from .store import Store
from .policy import money


class Trace:
    """Ordered, persisted log of everything the agent did in one run."""

    def __init__(self, store: Store, run_id: str) -> None:
        self.store = store
        self.run_id = run_id
        self.steps: list[dict[str, Any]] = []

    def add(self, kind: str, title: str, detail: str, **data: Any) -> dict[str, Any]:
        step = {
            "run_id": self.run_id,
            "seq": len(self.steps) + 1,
            "kind": kind,
            "title": title,
            "detail": detail,
            "ts": time.time(),
            "data": data,
        }
        self.steps.append(step)
        self.store.log_action(step)
        return step


def _authority(payload: dict[str, Any], stored: dict[str, Any]) -> dict[str, Any]:
    """Token limits are authoritative; revocation status is server-side."""
    authority: dict[str, Any] = {}
    for key in (
        "id",
        "agent",
        "currency",
        "budget",
        "per_txn_cap",
        "approval_threshold",
        "merchants",
        "categories",
        "max_purchases_per_hour",
        "expires_at",
    ):
        authority[key] = payload.get(key, stored.get(key))
    authority["status"] = stored.get("status", "active")
    return authority


def _pay(
    trace: Trace,
    store: Store,
    paypal: PayPalClient,
    *,
    mandate_id: str,
    run_id: str,
    offer: dict[str, Any],
    currency: str,
    approval_id: str | None = None,
) -> dict[str, Any]:
    price = float(offer["price"])
    trace.add(
        "payment",
        "Requesting payment",
        f"Opening a PayPal order for {money(price)} {currency} at {offer['merchant']}.",
        amount=price,
        merchant=offer["merchant"],
    )

    try:
        order = paypal.create_order(
            amount=price,
            currency=currency,
            description=f"{offer['name']} — {offer.get('merchant_name', offer['merchant'])}",
            custom_id=run_id,
            merchant=offer["merchant"],
        )
    except Exception as exc:  # noqa: BLE001 - surface any provider failure to the user
        trace.add("error", "PayPal rejected the order", str(exc))
        store.add_transaction(
            mandate_id=mandate_id,
            run_id=run_id,
            offer=offer,
            currency=currency,
            status="failed",
            error=str(exc),
            approval_id=approval_id,
        )
        if approval_id:
            store.resolve_approval(approval_id, "failed", str(exc))
        return {"verdict": "error", "reason": str(exc)}

    trace.add(
        "order",
        "PayPal order created",
        f"Order {order['id']} · status {order.get('status', 'CREATED')}",
        order_id=order["id"],
        mode=order.get("mode"),
    )

    try:
        capture = paypal.capture_order(order["id"])
    except Exception as exc:  # noqa: BLE001
        trace.add("error", "Capture failed", str(exc))
        store.add_transaction(
            mandate_id=mandate_id,
            run_id=run_id,
            offer=offer,
            currency=currency,
            status="failed",
            order_id=order["id"],
            error=str(exc),
            approval_id=approval_id,
        )
        if approval_id:
            store.resolve_approval(approval_id, "failed", str(exc))
        return {"verdict": "error", "reason": str(exc)}

    trace.add(
        "capture",
        "Payment captured",
        f"{capture.get('status', 'COMPLETED')} · capture {capture['id']}",
        capture_id=capture["id"],
        order_id=order["id"],
        mode=capture.get("mode", order.get("mode")),
    )

    transaction = store.add_transaction(
        mandate_id=mandate_id,
        run_id=run_id,
        offer=offer,
        currency=currency,
        status="completed",
        order_id=order["id"],
        capture_id=capture["id"],
        mode=capture.get("mode", order.get("mode")),
        approval_id=approval_id,
    )
    if approval_id:
        store.resolve_approval(approval_id, "approved")

    trace.add(
        "done",
        "Purchase complete",
        f"{offer['name']} from {offer['merchant']} for {money(price)}.",
        transaction_id=transaction["id"],
        amount=price,
    )
    return {
        "verdict": "paid",
        "reason": f"Paid {money(price)} for {offer['name']}.",
        "transaction": transaction,
    }


def run_agent(
    *,
    goal: str,
    mandate_id: str,
    settings: Settings,
    store: Store,
    paypal: PayPalClient,
    token_override: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    run_id = crypto.new_id("run")
    trace = Trace(store, run_id)

    stored = store.get_mandate(mandate_id)
    if not stored:
        trace.add("error", "Unknown mandate", f"No mandate with id {mandate_id}.")
        return trace.steps, {"verdict": "error", "reason": "Unknown mandate."}

    token = token_override or stored["token"]
    valid, payload, error = crypto.verify(token, settings.secret)
    if valid and payload and payload.get("id") != mandate_id:
        valid, error = False, "token was issued for a different mandate"

    trace.add(
        "verify",
        "Verifying capability token",
        "HMAC-SHA256 signature verified." if valid else f"Token rejected — {error}.",
        valid=valid,
        error=error,
    )

    if not valid or not payload:
        trace.add("block", "Spend blocked", "The gateway refused an unsigned or altered mandate.")
        return trace.steps, {
            "verdict": "block",
            "reason": f"Invalid capability token: {error or 'signature mismatch'}.",
        }

    authority = _authority(payload, stored)
    plan = ai.plan_goal(goal, settings)
    trace.add(
        "plan",
        f"{authority['agent']} is planning",
        plan["rationale"],
        goal=goal,
        strategy=plan["strategy"],
        category=plan["category"],
        max_price=plan["max_price"],
        keywords=plan["keywords"],
        source=plan["source"],
    )

    results = catalog.search_catalog(plan)
    if not results and plan.get("keywords"):
        trace.add(
            "search",
            "No exact match — widening the search",
            "Dropped keyword filters and searched the authorized category instead.",
        )
        plan = {**plan, "keywords": []}
        results = catalog.search_catalog(plan)

    if not results:
        trace.add(
            "block",
            "Nothing to buy",
            f"No offers matched “{goal}” within the requested parameters.",
        )
        return trace.steps, {"verdict": "block", "reason": "No matching offers."}

    preview = "; ".join(
        f"{item['name']} — {money(item['price'])} at {item['merchant']}" for item in results[:3]
    )
    trace.add(
        "search",
        f"Found {len(results)} candidate offers",
        f"Top matches: {preview}.",
        count=len(results),
        offers=[item["id"] for item in results[:6]],
    )

    spent = store.spent_for(mandate_id)
    velocity = store.purchases_last_hour(mandate_id)

    for offer in results[:6]:
        decision = policy.evaluate(
            mandate=authority,
            offer=offer,
            spent=spent,
            purchases_last_hour=velocity,
        )
        trace.add(
            "policy",
            f"Policy check · {offer['name']} at {offer['merchant']}",
            decision.reason,
            verdict=decision.verdict,
            checks=[check.to_dict() for check in decision.checks],
            offer=offer,
        )

        if decision.verdict == policy.BLOCK:
            trace.add(
                "block",
                "Skipped by policy",
                f"{offer['name']} ({money(offer['price'])}) at {offer['merchant']} — {decision.reason}",
                offer=offer,
            )
            continue

        if decision.verdict == policy.APPROVAL:
            approval = store.create_approval(
                mandate_id=mandate_id,
                run_id=run_id,
                offer=offer,
                reason=decision.reason,
            )
            trace.add(
                "approval",
                "Human approval required",
                f"{decision.reason} Requested {money(offer['price'])} for {offer['name']}.",
                approval_id=approval["id"],
                amount=approval["amount"],
                offer=offer,
            )
            return trace.steps, {
                "verdict": "approval",
                "reason": decision.reason,
                "approval": approval,
            }

        return trace.steps, _pay(
            trace,
            store,
            paypal,
            mandate_id=mandate_id,
            run_id=run_id,
            offer=offer,
            currency=authority.get("currency", "USD"),
        )

    trace.add(
        "block",
        "No payable offer",
        "Every candidate was outside the mandate. Nothing was charged.",
    )
    return trace.steps, {
        "verdict": "block",
        "reason": "Every candidate was outside the mandate.",
    }


def approve_request(
    *,
    approval_id: str,
    settings: Settings,
    store: Store,
    paypal: PayPalClient,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    approval = store.get_approval(approval_id)
    run_id = crypto.new_id("run")
    trace = Trace(store, run_id)

    if not approval:
        trace.add("error", "Unknown approval", "This approval request no longer exists.")
        return trace.steps, {"verdict": "error", "reason": "Unknown approval."}

    if approval["status"] != "pending":
        trace.add(
            "error",
            "Approval is not pending",
            f"This request is already {approval['status']}.",
        )
        return trace.steps, {"verdict": "error", "reason": "Approval is not pending."}

    mandate = store.get_mandate(approval["mandate_id"])
    if not mandate:
        trace.add("error", "Unknown mandate", "The mandate behind this approval is gone.")
        return trace.steps, {"verdict": "error", "reason": "Unknown mandate."}

    offer = approval["offer"]
    decision = policy.evaluate(
        mandate=mandate,
        offer=offer,
        spent=store.spent_for(approval["mandate_id"]),
        purchases_last_hour=store.purchases_last_hour(approval["mandate_id"]),
    )
    trace.add(
        "policy",
        f"Re-checking the mandate · {offer['name']}",
        decision.reason,
        verdict=decision.verdict,
        checks=[check.to_dict() for check in decision.checks],
        offer=offer,
    )

    if decision.verdict == policy.BLOCK:
        store.resolve_approval(approval_id, "expired", decision.reason)
        trace.add("block", "Approval void", f"The mandate changed before capture — {decision.reason}")
        return trace.steps, {"verdict": "block", "reason": decision.reason}

    trace.add(
        "approval",
        "Human approved",
        f"The owner approved {money(offer['price'])} for {offer['name']}.",
        approval_id=approval_id,
        amount=offer["price"],
        offer=offer,
    )

    return trace.steps, _pay(
        trace,
        store,
        paypal,
        mandate_id=approval["mandate_id"],
        run_id=run_id,
        offer=offer,
        currency=mandate.get("currency", "USD"),
        approval_id=approval_id,
    )


def deny_request(
    *, approval_id: str, store: Store
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    run_id = crypto.new_id("run")
    trace = Trace(store, run_id)
    approval = store.get_approval(approval_id)
    if not approval:
        trace.add("error", "Unknown approval", "This approval request no longer exists.")
        return trace.steps, {"verdict": "error", "reason": "Unknown approval."}
    if approval["status"] != "pending":
        trace.add("error", "Approval is not pending", f"This request is already {approval['status']}.")
        return trace.steps, {"verdict": "error", "reason": "Approval is not pending."}

    store.resolve_approval(approval_id, "denied", "Denied by the human owner.")
    trace.add(
        "deny",
        "Human denied the purchase",
        f"{approval['offer']['name']} was not purchased. Nothing was charged.",
        approval_id=approval_id,
        offer=approval["offer"],
    )
    return trace.steps, {"verdict": "denied", "reason": "Denied by the human owner."}
