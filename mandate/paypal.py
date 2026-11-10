"""PayPal Orders v2 client.

Real sandbox calls when credentials are configured; otherwise a deterministic
mock that returns PayPal-shaped responses so the whole product is demoable
with zero setup. The UI always shows which mode is active.
"""

from __future__ import annotations

import base64
import json
import random
import ssl
import string
import time
import urllib.error
import urllib.request
from typing import Any

from .config import Settings

SANDBOX_BASE = "https://api-m.sandbox.paypal.com"
LIVE_BASE = "https://api-m.paypal.com"


def _mock_order_id() -> str:
    alphabet = string.ascii_uppercase + string.digits
    body = "".join(random.choices(alphabet, k=15))
    return f"5O1{body}"


class PayPalClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._ssl = ssl.create_default_context()

    @property
    def mode(self) -> str:
        return self.settings.paypal_mode

    @property
    def base_url(self) -> str:
        if self.settings.paypal_api_base:
            return self.settings.paypal_api_base
        return LIVE_BASE if self.settings.paypal_env == "live" else SANDBOX_BASE

    # ------------------------------------------------------------------ auth
    def _token(self) -> str:
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token
        credentials = (
            f"{self.settings.paypal_client_id}:{self.settings.paypal_client_secret}"
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/v1/oauth2/token",
            data=b"grant_type=client_credentials",
            headers={
                "Authorization": "Basic " + base64.b64encode(credentials).decode("ascii"),
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=25, context=self._ssl) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self._access_token = payload["access_token"]
        self._token_expires_at = time.time() + float(payload.get("expires_in", 3600))
        return self._access_token

    def ping(self) -> None:
        """Acquire an OAuth token. Raises if the credentials are invalid."""
        self._token()

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={
                "Authorization": f"Bearer {self._token()}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30, context=self._ssl) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"PayPal {method} {path} failed ({exc.code}): {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"PayPal is unreachable: {exc.reason}") from exc

    # --------------------------------------------------------------- orders
    def create_order(
        self,
        *,
        amount: float,
        currency: str,
        description: str,
        custom_id: str,
        merchant: str,
    ) -> dict[str, Any]:
        if not self.settings.paypal_configured:
            time.sleep(0.45)
            return {
                "id": _mock_order_id(),
                "status": "CREATED",
                "mode": "mock",
                "debug": {"merchant": merchant, "custom_id": custom_id},
            }

        order = self._request(
            "POST",
            "/v2/checkout/orders",
            {
                "intent": "CAPTURE",
                "purchase_units": [
                    {
                        "amount": {"currency_code": currency, "value": f"{amount:.2f}"},
                        "description": description[:127],
                        "custom_id": custom_id[:127],
                    }
                ],
                "application_context": {
                    "brand_name": "Mandate",
                    "user_action": "PAY_NOW",
                    "shipping_preference": "NO_SHIPPING",
                },
            },
        )
        order["mode"] = "sandbox"
        return order

    def capture_order(self, order_id: str) -> dict[str, Any]:
        if not self.settings.paypal_configured:
            time.sleep(0.35)
            return {
                "id": _mock_order_id(),
                "status": "COMPLETED",
                "mode": "mock",
                "order_id": order_id,
            }

        capture = self._request("POST", f"/v2/checkout/orders/{order_id}/capture", {})
        capture["mode"] = "sandbox"
        capture["order_id"] = order_id
        return capture

    # -------------------------------------------------------------- webhooks
    def verify_webhook(self, headers: dict[str, str], event: dict[str, Any]) -> bool:
        """Verify a webhook signature with PayPal when configured."""
        if not self.settings.paypal_configured or not self.settings.paypal_webhook_id:
            return False
        try:
            result = self._request(
                "POST",
                "/v1/notifications/verify-webhook-signature",
                {
                    "auth_algo": headers.get("paypal-auth-algo", ""),
                    "cert_url": headers.get("paypal-cert-url", ""),
                    "transmission_id": headers.get("paypal-transmission-id", ""),
                    "transmission_sig": headers.get("paypal-transmission-sig", ""),
                    "transmission_time": headers.get("paypal-transmission-time", ""),
                    "webhook_id": self.settings.paypal_webhook_id,
                    "webhook_event": event,
                },
            )
            return result.get("verification_status") == "SUCCESS"
        except (RuntimeError, KeyError):
            return False
