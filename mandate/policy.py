"""The policy engine.

Pure functions, no I/O: given a mandate and an offer, decide whether the
agent may pay, must ask a human, or is blocked — and explain every check
that led to the verdict. The explanation is what makes the product
trustworthy, so the engine returns a full audit trail, not just a boolean.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

ALLOW = "allow"
APPROVAL = "approval"
BLOCK = "block"


def money(value: float) -> str:
    return f"${value:,.2f}"


def humanize_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{seconds}s"


@dataclass
class Check:
    id: str
    label: str
    status: str  # pass | fail | warn
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass
class Decision:
    verdict: str
    checks: list[Check]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "checks": [check.to_dict() for check in self.checks],
        }


def evaluate(
    *,
    mandate: dict[str, Any],
    offer: dict[str, Any],
    spent: float,
    purchases_last_hour: int = 0,
    now: float | None = None,
) -> Decision:
    now = time.time() if now is None else now
    checks: list[Check] = []

    def add(check_id: str, label: str, ok: bool, detail: str, *, warn: bool = False) -> bool:
        if warn:
            status = "warn"
        else:
            status = "pass" if ok else "fail"
        checks.append(Check(check_id, label, status, detail))
        return ok

    price = float(offer["price"])
    currency = mandate.get("currency", "USD")

    status_ok = (mandate.get("status") or "active") == "active"
    add(
        "status",
        "Mandate status",
        status_ok,
        "Active — the owner has not revoked this mandate."
        if status_ok
        else "Revoked by the human owner. No further spending is authorized.",
    )

    expires_at = float(mandate.get("expires_at") or 0)
    not_expired = now < expires_at
    add(
        "expiry",
        "Expiry",
        not_expired,
        f"Valid for another {humanize_duration(expires_at - now)}."
        if not_expired
        else "The mandate has expired.",
    )

    merchants = [m.strip().lower() for m in (mandate.get("merchants") or []) if str(m).strip()]
    merchant_ok = not merchants or offer["merchant"].lower() in merchants
    if not merchants:
        merchant_detail = "No merchant restriction on this mandate."
    elif merchant_ok:
        merchant_detail = f"{offer['merchant']} is on the allowlist."
    else:
        merchant_detail = (
            f"{offer['merchant']} is not on the allowlist ({', '.join(merchants)})."
        )
    add("merchant", "Merchant allowlist", merchant_ok, merchant_detail)

    categories = [c.strip().lower() for c in (mandate.get("categories") or []) if str(c).strip()]
    category_ok = not categories or offer["category"].lower() in categories
    if not categories:
        category_detail = "No category restriction on this mandate."
    elif category_ok:
        category_detail = f"{offer['category']} is an authorized category."
    else:
        category_detail = (
            f"{offer['category']} is outside the authorized categories "
            f"({', '.join(categories)})."
        )
    add("category", "Category", category_ok, category_detail)

    cap = float(mandate.get("per_txn_cap") or 0)
    cap_ok = price <= cap + 1e-9
    add(
        "cap",
        "Per-transaction cap",
        cap_ok,
        f"{money(price)} is {'within' if cap_ok else 'above'} the {money(cap)} per-transaction cap.",
    )

    budget = float(mandate.get("budget") or 0)
    projected = spent + price
    budget_ok = projected <= budget + 1e-9
    add(
        "budget",
        "Remaining budget",
        budget_ok,
        f"{money(spent)} spent + {money(price)} = {money(projected)} of {money(budget)}"
        + ("." if budget_ok else " — over budget."),
    )

    velocity_cap = int(mandate.get("max_purchases_per_hour") or 0)
    velocity_ok = velocity_cap <= 0 or purchases_last_hour < velocity_cap
    add(
        "velocity",
        "Velocity limit",
        velocity_ok,
        f"{purchases_last_hour} of {velocity_cap} purchases used in the last hour."
        if velocity_cap
        else "No velocity limit set.",
    )

    hard_failures = [check for check in checks if check.status == "fail"]
    if hard_failures:
        return Decision(BLOCK, checks, hard_failures[0].detail)

    threshold = float(mandate.get("approval_threshold") or 0)
    needs_approval = price > threshold + 1e-9
    add(
        "approval",
        "Human approval threshold",
        not needs_approval,
        f"{money(price)} is below the {money(threshold)} auto-approve threshold."
        if not needs_approval
        else f"{money(price)} is above the {money(threshold)} auto-approve threshold — a human must approve.",
        warn=needs_approval,
    )

    if needs_approval:
        return Decision(
            APPROVAL,
            checks,
            f"Above the {money(threshold)} auto-approve threshold.",
        )

    return Decision(
        ALLOW,
        checks,
        f"Within mandate — {money(price)} {currency} is auto-approved.",
    )
