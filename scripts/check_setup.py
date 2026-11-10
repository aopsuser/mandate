#!/usr/bin/env python3
"""Diagnose Mandate configuration and connectivity.

    python3 scripts/check_setup.py

Reports which modes are active, verifies PayPal credentials if provided,
and tests the LLM endpoint if configured. Never prints secrets.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mandate.config import DATA_DIR, load_dotenv, load_settings  # noqa: E402
from mandate.paypal import PayPalClient  # noqa: E402

OK = "✓"
WARN = "!"
BAD = "✗"


def main() -> int:
    load_dotenv()
    settings = load_settings()
    failures = 0

    print()
    print("  Mandate setup check")
    print("  " + "─" * 19)

    print(f"  {OK} Python {sys.version.split()[0]}")
    print(f"  {OK} Project root: {ROOT}")

    env_file = ROOT / ".env"
    if env_file.exists():
        print(f"  {OK} .env found")
    else:
        print(f"  {WARN} .env not found — copy .env.example to .env if you want to add keys")

    state_file = DATA_DIR / "state.json"
    print(
        f"  {OK} State: {'present' if state_file.exists() else 'will be created on first run'}"
    )
    secret_source = "MANDATE_SECRET env" if os.environ.get("MANDATE_SECRET") else "data/.secret"
    print(f"  {OK} Signing key: {secret_source}")

    print()
    print("  PayPal")
    print(f"    mode: {settings.paypal_mode}   environment: {settings.paypal_env}")
    if not settings.paypal_configured:
        print(f"    {WARN} No credentials — using mock payments.")
        print("       Every flow still works. To use the sandbox:")
        print("       1. https://developer.paypal.com/dashboard/applications/sandbox")
        print("       2. put PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in .env")
        print("       3. re-run this script")
    else:
        try:
            client = PayPalClient(settings)
            client.ping()
            print(f"    {OK} OAuth token acquired — credentials are valid")
            print(f"       Orders endpoint: {client.base_url}")
        except Exception as exc:  # noqa: BLE001 - diagnostic output
            failures += 1
            print(f"    {BAD} Credential check failed: {exc}")

    print()
    print("  AI planner")
    if not settings.llm_api_key:
        print(f"    {WARN} No LLM key — using the deterministic heuristic planner.")
        print("       The demo is fully functional. To use a model:")
        print("       set LLM_API_KEY (and optionally LLM_BASE_URL / LLM_MODEL) in .env")
    else:
        url = f"{settings.llm_base_url}/models"
        request = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {settings.llm_api_key}"}
        )
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                response.read()
            print(f"    {OK} {settings.llm_model} via {settings.llm_base_url}")
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                failures += 1
                print(f"    {BAD} Key rejected by {url} ({exc.code})")
            else:
                print(f"    {WARN} Endpoint responded {exc.code}; some providers do not expose /models")
                print("       The planner may still work — run a goal in the app to confirm.")
        except Exception as exc:  # noqa: BLE001
            print(f"    {WARN} Could not reach {url}: {exc}")
            print("       The planner may still work — run a goal in the app to confirm.")

    print()
    print("  Run the app:  python3 app.py")
    print("  Open:         http://127.0.0.1:3000")
    print()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
