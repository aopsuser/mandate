"""Capability token tests — run with: python3 -m unittest discover -s tests"""

from __future__ import annotations

import base64
import json
import unittest

from mandate import crypto

SECRET = "test-secret-do-not-use-in-production"


class CryptoTests(unittest.TestCase):
    def test_roundtrip(self):
        payload = {"id": "mnd_1", "budget": 300}
        token = crypto.sign(payload, SECRET)
        valid, decoded, error = crypto.verify(token, SECRET)
        self.assertTrue(valid)
        self.assertIsNone(error)
        self.assertEqual(decoded, payload)

    def test_wrong_secret_fails(self):
        token = crypto.sign({"id": "mnd_1"}, SECRET)
        valid, _, error = crypto.verify(token, "another-secret")
        self.assertFalse(valid)
        self.assertEqual(error, "signature mismatch")

    def test_tampered_payload_fails(self):
        token = crypto.sign({"id": "mnd_1", "budget": 50}, SECRET)
        body, signature = token.split(".")
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        payload["budget"] = 99999
        forged_body = (
            base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
            .rstrip(b"=")
            .decode()
        )
        valid, _, error = crypto.verify(f"{forged_body}.{signature}", SECRET)
        self.assertFalse(valid)
        self.assertEqual(error, "signature mismatch")

    def test_malformed_tokens_fail_cleanly(self):
        for bad in ["", "nope", "a.b.c", "!!!.@@@"]:
            valid, payload, _ = crypto.verify(bad, SECRET)
            self.assertFalse(valid)
            self.assertIsNone(payload)

    def test_token_is_deterministic_for_same_payload(self):
        payload = {"b": 2, "a": 1}
        self.assertEqual(crypto.sign(payload, SECRET), crypto.sign({"a": 1, "b": 2}, SECRET))


if __name__ == "__main__":
    unittest.main()
