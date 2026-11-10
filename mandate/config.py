"""Runtime configuration.

Everything is optional: with no configuration at all the app runs in
mock-payment / heuristic-agent mode, which is enough to demo every flow.
Set PayPal sandbox credentials to move real (sandbox) money, and an
LLM key to swap the heuristic planner for a model-driven one.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


def load_dotenv(path: Path | None = None) -> None:
    """Minimal .env loader so the project needs no third-party packages."""
    path = path or (ROOT / ".env")
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _persistent_secret() -> str:
    """Stable HMAC key for signing mandate capability tokens.

    Generated once and stored under data/ so tokens survive restarts.
    In a real deployment this would live in a KMS, never on disk.
    """
    configured = os.environ.get("MANDATE_SECRET", "").strip()
    if configured:
        return configured

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / ".secret"
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value

    value = secrets.token_urlsafe(48)
    path.write_text(value, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return value


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    secret: str
    paypal_client_id: str
    paypal_client_secret: str
    paypal_env: str
    paypal_webhook_id: str
    paypal_api_base: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str

    @property
    def paypal_configured(self) -> bool:
        return bool(self.paypal_client_id and self.paypal_client_secret)

    @property
    def paypal_mode(self) -> str:
        return "sandbox" if self.paypal_configured else "mock"

    @property
    def ai_mode(self) -> str:
        return "llm" if self.llm_api_key else "heuristic"

    @property
    def ai_label(self) -> str:
        if self.llm_api_key:
            return self.llm_model
        return "heuristic planner"


def _ensure_ca_bundle() -> None:
    """Point OpenSSL at the OS trust store when Python ships without one.

    The python.org macOS installer does not install a CA bundle, so
    ``ssl.create_default_context()`` fails with CERTIFICATE_VERIFY_FAILED
    until the user runs "Install Certificates.command". Falling back to the
    system bundle keeps PayPal and LLM calls working out of the box.
    """
    if os.environ.get("SSL_CERT_FILE"):
        return
    for candidate in ("/etc/ssl/cert.pem", "/usr/local/etc/openssl/cert.pem"):
        if Path(candidate).is_file():
            os.environ["SSL_CERT_FILE"] = candidate
            return


def load_settings() -> Settings:
    _ensure_ca_bundle()
    return Settings(
        host=os.environ.get("HOST", "127.0.0.1").strip(),
        port=int(os.environ.get("PORT", "3000")),
        secret=_persistent_secret(),
        paypal_client_id=os.environ.get("PAYPAL_CLIENT_ID", "").strip(),
        paypal_client_secret=os.environ.get("PAYPAL_CLIENT_SECRET", "").strip(),
        paypal_env=os.environ.get("PAYPAL_ENV", "sandbox").strip().lower(),
        paypal_webhook_id=os.environ.get("PAYPAL_WEBHOOK_ID", "").strip(),
        paypal_api_base=os.environ.get("PAYPAL_API_BASE", "").strip().rstrip("/"),
        llm_api_key=os.environ.get("LLM_API_KEY", "").strip(),
        llm_base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        llm_model=os.environ.get("LLM_MODEL", "gpt-4o-mini").strip(),
    )
