#!/usr/bin/env python3
"""Mandate HTTP server — Python standard library only.

Run it:
    python3 app.py
Then open http://127.0.0.1:3000
"""

from __future__ import annotations

import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from mandate import agent as agent_mod
from mandate import catalog, crypto
from mandate.config import ROOT, load_dotenv, load_settings
from mandate.paypal import PayPalClient
from mandate.store import Store

load_dotenv()
SETTINGS = load_settings()
STORE = Store(secret=SETTINGS.secret)
PAYPAL = PayPalClient(SETTINGS)
PUBLIC = ROOT / "public"

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}

ROUTE_MANDATE = re.compile(r"^/api/mandates/([A-Za-z0-9_\-]+)/(revoke|topup)$")
ROUTE_APPROVAL = re.compile(r"^/api/approvals/([A-Za-z0-9_\-]+)/(approve|deny)$")


class Handler(BaseHTTPRequestHandler):
    server_version = "Mandate/1.0"

    # ------------------------------------------------------------- plumbing
    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"  {self.command:<2} {self.path}", flush=True)

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._json({"error": message}, status=status)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 1_000_000:
            raise ValueError("request body is too large")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid JSON body") from exc
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _state(self) -> dict[str, Any]:
        snapshot = STORE.snapshot()
        snapshot["paypal"] = {
            "mode": PAYPAL.mode,
            "configured": SETTINGS.paypal_configured,
            "env": SETTINGS.paypal_env,
        }
        snapshot["ai"] = {"mode": SETTINGS.ai_mode, "label": SETTINGS.ai_label}
        snapshot["server_time"] = time.time()
        return snapshot

    def _static(self, path: str) -> None:
        relative = unquote(path.lstrip("/")) or "index.html"
        root = PUBLIC.resolve()
        target = (root / relative).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return self._error(404, "not found")
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            return self._error(404, "not found")
        data = target.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type",
            MIME_TYPES.get(target.suffix.lower(), "application/octet-stream"),
        )
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # ---------------------------------------------------------------- routes
    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path
        if path == "/api/health":
            return self._json({"ok": True, "mode": PAYPAL.mode, "ai": SETTINGS.ai_mode})
        if path == "/api/state":
            return self._json(self._state())
        if path == "/api/catalog":
            return self._json({"items": catalog.CATALOG, "merchants": catalog.MERCHANTS})
        if path.startswith("/api/"):
            return self._error(404, "unknown endpoint")
        return self._static(path)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        path = urlparse(self.path).path
        try:
            body = self._read_body()
        except ValueError as exc:
            return self._error(400, str(exc))

        try:
            if path == "/api/agent/run":
                return self._run_agent(body)

            if path == "/api/mandates":
                return self._create_mandate(body)

            if path == "/api/verify":
                token = str(body.get("token") or "")
                valid, payload, error = crypto.verify(token, SETTINGS.secret)
                return self._json(
                    {"valid": valid, "error": error, "payload": payload if valid else None}
                )

            if path == "/api/reset":
                STORE.reset()
                return self._json({"ok": True, "state": self._state()})

            if path == "/api/webhooks/paypal":
                event = body
                headers = {key.lower(): value for key, value in self.headers.items()}
                verified = PAYPAL.verify_webhook(headers, event)
                STORE.log_action(
                    {
                        "run_id": "webhook",
                        "seq": 0,
                        "kind": "webhook",
                        "title": "PayPal webhook received",
                        "detail": f"{event.get('event_type', 'unknown event')} · "
                        f"{'signature verified' if verified else 'unverified (demo mode)'}",
                        "ts": time.time(),
                        "data": {"event_type": event.get("event_type")},
                    }
                )
                return self._json({"ok": True, "verified": verified})

            mandate_match = ROUTE_MANDATE.match(path)
            if mandate_match:
                mandate_id, action = mandate_match.groups()
                if action == "revoke":
                    view = STORE.revoke(mandate_id)
                    if not view:
                        return self._error(404, "mandate not found")
                    return self._json({"mandate": view, "state": self._state()})
                amount = float(body.get("amount") or 75)
                if amount <= 0 or amount > 10_000:
                    return self._error(400, "top-up amount must be between 0 and 10000")
                view = STORE.topup(mandate_id, amount)
                if not view:
                    return self._error(404, "mandate not found")
                return self._json({"mandate": view, "state": self._state()})

            approval_match = ROUTE_APPROVAL.match(path)
            if approval_match:
                approval_id, action = approval_match.groups()
                if action == "approve":
                    steps, result = agent_mod.approve_request(
                        approval_id=approval_id,
                        settings=SETTINGS,
                        store=STORE,
                        paypal=PAYPAL,
                    )
                else:
                    steps, result = agent_mod.deny_request(
                        approval_id=approval_id, store=STORE
                    )
                return self._json({"steps": steps, "result": result, "state": self._state()})

            return self._error(404, "unknown endpoint")
        except ValueError as exc:
            return self._error(400, str(exc))
        except Exception as exc:  # noqa: BLE001 - demo server: surface, don't crash
            print(f"  !! {type(exc).__name__}: {exc}", flush=True)
            return self._error(500, f"{type(exc).__name__}: {exc}")

    # --------------------------------------------------------------- actions
    def _run_agent(self, body: dict[str, Any]) -> None:
        goal = str(body.get("goal") or "").strip()
        if not (3 <= len(goal) <= 500):
            raise ValueError("goal must be between 3 and 500 characters")

        mandate_id = str(body.get("mandate_id") or STORE.first_mandate_id() or "")
        if not mandate_id:
            raise ValueError("no mandate available")

        token_override = body.get("token_override")
        if token_override is not None and not isinstance(token_override, str):
            raise ValueError("token_override must be a string")

        steps, result = agent_mod.run_agent(
            goal=goal,
            mandate_id=mandate_id,
            settings=SETTINGS,
            store=STORE,
            paypal=PAYPAL,
            token_override=token_override,
        )
        return self._json({"steps": steps, "result": result, "state": self._state()})

    def _create_mandate(self, body: dict[str, Any]) -> None:
        budget = float(body.get("budget") or 0)
        cap = float(body.get("per_txn_cap") or 0)
        threshold = float(body.get("approval_threshold") or 0)
        if budget <= 0 or cap <= 0:
            raise ValueError("budget and per_txn_cap must be positive")
        if cap > budget:
            raise ValueError("per_txn_cap cannot exceed the total budget")
        if threshold > cap:
            raise ValueError("approval_threshold cannot exceed the per-transaction cap")

        view = STORE.create_mandate(
            {
                "agent": body.get("agent"),
                "currency": body.get("currency"),
                "budget": budget,
                "per_txn_cap": cap,
                "approval_threshold": threshold,
                "merchants": body.get("merchants") or [],
                "categories": body.get("categories") or [],
                "max_purchases_per_hour": body.get("max_purchases_per_hour") or 12,
                "expires_in_hours": body.get("expires_in_hours") or 24,
            }
        )
        return self._json({"mandate": view, "state": self._state()}, status=201)


def main() -> None:
    server = ThreadingHTTPServer((SETTINGS.host, SETTINGS.port), Handler)
    paypal_line = (
        f"PayPal sandbox · {'configured' if SETTINGS.paypal_configured else 'MOCK (no credentials)'}"
    )
    ai_line = f"Agent planner · {SETTINGS.ai_label}"
    print()
    print("  MANDATE — spend authority for autonomous agents")
    print(f"  → http://{SETTINGS.host}:{SETTINGS.port}")
    print(f"  · {paypal_line}")
    print(f"  · {ai_line}")
    print("  Ctrl+C to stop\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
