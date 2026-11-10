"""Persistence: a single JSON document behind a lock.

Deliberately boring. Hackathon judges should be able to read state.json and
understand exactly what happened, and the whole app should survive a restart.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from . import crypto
from .config import DATA_DIR

TOKEN_FIELDS = (
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
)

MAX_ACTIONS = 400


def issue_token(mandate: dict[str, Any], secret: str) -> str:
    payload = {key: mandate[key] for key in TOKEN_FIELDS}
    payload["iat"] = int(mandate.get("created_at") or time.time())
    payload["v"] = 1
    return crypto.sign(payload, secret)


class Store:
    def __init__(self, *, secret: str, path: Path | None = None) -> None:
        self.secret = secret
        self.path = path or (DATA_DIR / "state.json")
        self._lock = threading.RLock()
        self.state: dict[str, Any] = {}
        self.state = self._load()

    # ------------------------------------------------------------ lifecycle
    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "mandates" in data:
                    for mandate in data["mandates"].values():
                        if not mandate.get("token"):
                            mandate["token"] = issue_token(mandate, self.secret)
                    data.setdefault("transactions", [])
                    data.setdefault("approvals", [])
                    data.setdefault("actions", [])
                    self.state = data
                    return data
            except (json.JSONDecodeError, OSError, KeyError):
                pass
        return self._seed()

    def _seed(self) -> dict[str, Any]:
        now = time.time()
        mandate: dict[str, Any] = {
            "id": "mnd_scout_01",
            "agent": "Scout",
            "currency": "USD",
            "budget": 400.00,
            "per_txn_cap": 150.00,
            "approval_threshold": 100.00,
            "merchants": ["stride.run", "runnersdepot.com"],
            "categories": ["footwear"],
            "max_purchases_per_hour": 12,
            "expires_at": now + 24 * 3600,
            "status": "active",
            "created_at": now,
        }
        mandate["token"] = issue_token(mandate, self.secret)
        self.state = {
            "version": 1,
            "created_at": now,
            "mandates": {mandate["id"]: mandate},
            "transactions": [],
            "approvals": [],
            "actions": [],
        }
        self._save()
        return self.state

    def reset(self) -> dict[str, Any]:
        with self._lock:
            return self._seed()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, indent=1), encoding="utf-8")
        os.replace(temporary, self.path)

    # -------------------------------------------------------------- readers
    def get_mandate(self, mandate_id: str) -> dict[str, Any] | None:
        with self._lock:
            mandate = self.state["mandates"].get(mandate_id)
            return dict(mandate) if mandate else None

    def first_mandate_id(self) -> str | None:
        with self._lock:
            return next(iter(self.state["mandates"]), None)

    def spent_for(self, mandate_id: str) -> float:
        with self._lock:
            return round(
                sum(
                    float(txn["amount"])
                    for txn in self.state["transactions"]
                    if txn["mandate_id"] == mandate_id and txn["status"] == "completed"
                ),
                2,
            )

    def purchases_last_hour(self, mandate_id: str) -> int:
        cutoff = time.time() - 3600
        with self._lock:
            return sum(
                1
                for txn in self.state["transactions"]
                if txn["mandate_id"] == mandate_id
                and txn["status"] == "completed"
                and txn["created_at"] >= cutoff
            )

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        with self._lock:
            approval = next(
                (a for a in self.state["approvals"] if a["id"] == approval_id), None
            )
            return dict(approval) if approval else None

    # ------------------------------------------------------------- mutations
    def create_mandate(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        mandate: dict[str, Any] = {
            "id": crypto.new_id("mnd"),
            "agent": str(payload.get("agent") or "Agent")[:40],
            "currency": str(payload.get("currency") or "USD")[:8],
            "budget": float(payload.get("budget") or 0),
            "per_txn_cap": float(payload.get("per_txn_cap") or 0),
            "approval_threshold": float(payload.get("approval_threshold") or 0),
            "merchants": [str(m).strip().lower() for m in (payload.get("merchants") or []) if str(m).strip()],
            "categories": [str(c).strip().lower() for c in (payload.get("categories") or []) if str(c).strip()],
            "max_purchases_per_hour": int(payload.get("max_purchases_per_hour") or 0),
            "expires_at": now + float(payload.get("expires_in_hours") or 24) * 3600,
            "status": "active",
            "created_at": now,
        }
        mandate["token"] = issue_token(mandate, self.secret)
        with self._lock:
            self.state["mandates"][mandate["id"]] = mandate
            self.log_action(
                {
                    "run_id": "system",
                    "seq": 0,
                    "kind": "issue",
                    "title": "Mandate issued",
                    "detail": f"{mandate['agent']} authorized to spend up to "
                    f"${mandate['budget']:,.2f} across {len(mandate['merchants']) or 'any'} merchants.",
                    "ts": now,
                    "data": {"mandate_id": mandate["id"]},
                }
            )
            self._save()
            return self._view(mandate)

    def revoke(self, mandate_id: str) -> dict[str, Any] | None:
        with self._lock:
            mandate = self.state["mandates"].get(mandate_id)
            if not mandate:
                return None
            mandate["status"] = "revoked"
            self.log_action(
                {
                    "run_id": "system",
                    "seq": 0,
                    "kind": "revoke",
                    "title": "Mandate revoked",
                    "detail": "The human owner revoked spending authority. Outstanding approvals are void.",
                    "ts": time.time(),
                    "data": {"mandate_id": mandate_id},
                }
            )
            for approval in self.state["approvals"]:
                if approval["mandate_id"] == mandate_id and approval["status"] == "pending":
                    approval["status"] = "void"
                    approval["resolved_at"] = time.time()
                    approval["note"] = "Mandate revoked before approval."
            self._save()
            return self._view(mandate)

    def topup(self, mandate_id: str, amount: float) -> dict[str, Any] | None:
        with self._lock:
            mandate = self.state["mandates"].get(mandate_id)
            if not mandate:
                return None
            mandate["budget"] = round(float(mandate["budget"]) + abs(float(amount)), 2)
            mandate["token"] = issue_token(mandate, self.secret)  # limits change => new signature
            self.log_action(
                {
                    "run_id": "system",
                    "seq": 0,
                    "kind": "topup",
                    "title": "Mandate re-issued",
                    "detail": f"Budget raised to ${mandate['budget']:,.2f}. A new signed token was issued — the agent never touches the signing key.",
                    "ts": time.time(),
                    "data": {"mandate_id": mandate_id, "budget": mandate["budget"]},
                }
            )
            self._save()
            return self._view(mandate)

    def add_transaction(
        self,
        *,
        mandate_id: str,
        run_id: str,
        offer: dict[str, Any],
        currency: str,
        status: str,
        order_id: str | None = None,
        capture_id: str | None = None,
        mode: str | None = None,
        error: str | None = None,
        approval_id: str | None = None,
    ) -> dict[str, Any]:
        transaction = {
            "id": crypto.new_id("txn"),
            "mandate_id": mandate_id,
            "run_id": run_id,
            "item_id": offer["id"],
            "item_name": offer["name"],
            "merchant": offer["merchant"],
            "merchant_name": offer.get("merchant_name", offer["merchant"]),
            "amount": round(float(offer["price"]), 2),
            "currency": currency,
            "status": status,
            "paypal_order_id": order_id,
            "paypal_capture_id": capture_id,
            "mode": mode,
            "error": error,
            "approval_id": approval_id,
            "created_at": time.time(),
        }
        with self._lock:
            self.state["transactions"].append(transaction)
            self._save()
        return transaction

    def create_approval(
        self, *, mandate_id: str, run_id: str, offer: dict[str, Any], reason: str
    ) -> dict[str, Any]:
        with self._lock:
            for approval in self.state["approvals"]:
                if (
                    approval["mandate_id"] == mandate_id
                    and approval["status"] == "pending"
                    and approval["offer"]["id"] == offer["id"]
                ):
                    return dict(approval)

            approval = {
                "id": crypto.new_id("apr"),
                "mandate_id": mandate_id,
                "run_id": run_id,
                "offer": dict(offer),
                "amount": round(float(offer["price"]), 2),
                "reason": reason,
                "status": "pending",
                "created_at": time.time(),
                "resolved_at": None,
                "note": None,
            }
            self.state["approvals"].append(approval)
            self._save()
            return dict(approval)

    def resolve_approval(self, approval_id: str, status: str, note: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            for approval in self.state["approvals"]:
                if approval["id"] == approval_id:
                    approval["status"] = status
                    approval["resolved_at"] = time.time()
                    approval["note"] = note
                    self._save()
                    return dict(approval)
            return None

    def log_action(self, step: dict[str, Any]) -> None:
        with self._lock:
            self.state["actions"].append(step)
            if len(self.state["actions"]) > MAX_ACTIONS:
                self.state["actions"] = self.state["actions"][-MAX_ACTIONS:]
            self._save()

    # -------------------------------------------------------------- snapshot
    def _view(self, mandate: dict[str, Any]) -> dict[str, Any]:
        mandate_id = mandate["id"]
        spent = self.spent_for(mandate_id)
        pending = sum(
            1
            for approval in self.state["approvals"]
            if approval["mandate_id"] == mandate_id and approval["status"] == "pending"
        )
        return {
            **mandate,
            "spent": spent,
            "remaining": round(max(0.0, float(mandate["budget"]) - spent), 2),
            "expires_in": int(max(0, float(mandate["expires_at"]) - time.time())),
            "purchases_last_hour": self.purchases_last_hour(mandate_id),
            "pending_approvals": pending,
            "token_preview": crypto.token_preview(mandate["token"]),
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            mandates = [self._view(m) for m in self.state["mandates"].values()]
            transactions = list(reversed(self.state["transactions"][-40:]))
            approvals = list(reversed(self.state["approvals"][-20:]))
            actions = list(self.state["actions"][-80:])
            stats = {
                "captured": round(
                    sum(
                        float(txn["amount"])
                        for txn in self.state["transactions"]
                        if txn["status"] == "completed"
                    ),
                    2,
                ),
                "payments": sum(
                    1 for txn in self.state["transactions"] if txn["status"] == "completed"
                ),
                "blocked": sum(1 for action in self.state["actions"] if action["kind"] == "block"),
                "pending": sum(1 for a in self.state["approvals"] if a["status"] == "pending"),
                "approvals": len(self.state["approvals"]),
                "runs": len({action["run_id"] for action in self.state["actions"]}),
            }
            return {
                "mandate": mandates[0] if mandates else None,
                "mandates": mandates,
                "transactions": transactions,
                "approvals": approvals,
                "actions": actions,
                "stats": stats,
                "server_time": time.time(),
            }
