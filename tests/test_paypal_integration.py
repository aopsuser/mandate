"""PayPal client integration test against a local stub server.

This exercises the *real* Orders v2 code path — OAuth token acquisition,
order creation, capture, headers, payload shape, and token caching — without
needing sandbox credentials. The client is pointed at a local HTTP server via
PAYPAL_API_BASE, which is the same override available for manual testing.
"""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from mandate.config import Settings
from mandate.paypal import PayPalClient


class StubPayPal(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def log_message(self, *args) -> None:  # keep test output clean
        pass

    def _send(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - handler API
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            body = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"_raw": raw}

        type(self).requests.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization", ""),
                "content_type": self.headers.get("Content-Type", ""),
                "body": body,
            }
        )

        if self.path == "/v1/oauth2/token":
            self._send({"access_token": "fake-access-token", "expires_in": 3600})
        elif self.path == "/v2/checkout/orders":
            self._send({"id": "ORDER-123", "status": "CREATED"})
        elif self.path.startswith("/v2/checkout/orders/"):
            if "MISSING" in self.path:
                self.send_error(404)
            elif self.path.endswith("/capture"):
                self._send({"id": "CAPTURE-456", "status": "COMPLETED"})
            else:
                self.send_error(404)
        else:
            self.send_error(404)


def settings_for(port: int, *, credentials: bool = True) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=0,
        secret="test-secret",
        paypal_client_id="client-id" if credentials else "",
        paypal_client_secret="client-secret" if credentials else "",
        paypal_env="sandbox",
        paypal_webhook_id="",
        paypal_api_base=f"http://127.0.0.1:{port}" if credentials else "",
        llm_api_key="",
        llm_base_url="",
        llm_model="",
    )


class PayPalIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), StubPayPal)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        StubPayPal.requests = []

    def test_create_and_capture_flow(self) -> None:
        client = PayPalClient(settings_for(self.port))

        order = client.create_order(
            amount=118.0,
            currency="USD",
            description="Aero Tempo 4",
            custom_id="run_abc",
            merchant="stride.run",
        )
        self.assertEqual(order["id"], "ORDER-123")
        self.assertEqual(order["status"], "CREATED")
        self.assertEqual(order["mode"], "sandbox")

        capture = client.capture_order(order["id"])
        self.assertEqual(capture["id"], "CAPTURE-456")
        self.assertEqual(capture["status"], "COMPLETED")
        self.assertEqual(capture["mode"], "sandbox")

        paths = [request["path"] for request in StubPayPal.requests]
        self.assertEqual(
            paths,
            [
                "/v1/oauth2/token",
                "/v2/checkout/orders",
                "/v2/checkout/orders/ORDER-123/capture",
            ],
        )

        token_request, order_request, capture_request = StubPayPal.requests

        self.assertTrue(token_request["authorization"].startswith("Basic "))
        self.assertEqual(token_request["content_type"], "application/x-www-form-urlencoded")

        self.assertEqual(order_request["authorization"], "Bearer fake-access-token")
        self.assertEqual(order_request["body"]["intent"], "CAPTURE")
        unit = order_request["body"]["purchase_units"][0]
        self.assertEqual(unit["amount"], {"currency_code": "USD", "value": "118.00"})
        self.assertEqual(unit["description"], "Aero Tempo 4")
        self.assertEqual(unit["custom_id"], "run_abc")

        self.assertEqual(capture_request["authorization"], "Bearer fake-access-token")
        self.assertEqual(capture_request["body"], {})

    def test_access_token_is_cached_across_requests(self) -> None:
        client = PayPalClient(settings_for(self.port))
        client.create_order(
            amount=10.0, currency="USD", description="one", custom_id="1", merchant="a"
        )
        client.create_order(
            amount=20.0, currency="USD", description="two", custom_id="2", merchant="b"
        )
        token_requests = [
            request for request in StubPayPal.requests if request["path"] == "/v1/oauth2/token"
        ]
        self.assertEqual(len(token_requests), 1)

    def test_mock_mode_needs_no_credentials(self) -> None:
        client = PayPalClient(settings_for(0, credentials=False))
        self.assertEqual(client.mode, "mock")
        order = client.create_order(
            amount=5.0, currency="USD", description="mock", custom_id="m", merchant="x"
        )
        self.assertEqual(order["mode"], "mock")
        self.assertTrue(order["id"].startswith("5O1"))

    def test_http_error_becomes_readable_runtime_error(self) -> None:
        client = PayPalClient(settings_for(self.port))
        with self.assertRaises(RuntimeError) as caught:
            client.capture_order("MISSING-ORDER")
        self.assertIn("404", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
