"""Runtime configuration and model-provider selection.

The agent must keep working while provider access is still being sorted out, so the
model provider is discovered at runtime rather than hard-coded.  Order of preference:

1. ``mantle``    - Bedrock Projects OpenAI-compatible endpoint (works on the free plan)
2. ``bedrock``   - classic bedrock-runtime
2. ``ollama``    - free, local, no account
3. ``anthropic`` - paid fallback
4. ``none``      - deterministic policy only; the demo still runs end to end
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_BEDROCK_MODEL = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
# Bedrock Projects ("mantle") exposes an OpenAI-compatible endpoint that works with a
# Mantle API key on the free account plan, where classic bedrock-runtime does not.
DEFAULT_MANTLE_MODEL = "google.gemma-4-31b"
MANTLE_BASE_URL = "https://bedrock-mantle.{region}.api.aws/openai/v1"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"


def load_env(path: Path | None = None) -> None:
    """Load .env without adding a dependency, and never overwrite a real env var."""
    env_path = path or PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


@dataclass(frozen=True)
class Settings:
    calle_api_key: str = ""
    demo_phone_number: str = ""
    aws_region: str = "eu-central-1"
    ollama_host: str = "http://localhost:11434"
    anthropic_api_key: str = ""
    language: str = "de"

    @classmethod
    def from_env(cls) -> "Settings":
        load_env()
        return cls(
            calle_api_key=os.environ.get("CALLE_API_KEY", "").strip(),
            demo_phone_number=os.environ.get("DEMO_PHONE_NUMBER", "").strip(),
            aws_region=os.environ.get("AWS_REGION", "eu-central-1").strip(),
            ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434").strip(),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip(),
            # Import defaults keep the German-farmer workflow intact. The browser
            # separately defaults its judge-facing console and demo callback to English.
            language=os.environ.get("ACREVOICE_LANGUAGE", "de").strip(),
        )

    @property
    def has_calle(self) -> bool:
        return bool(self.calle_api_key)


def _bedrock_available(settings: Settings) -> bool:
    """Bedrock counts as available only if a model actually answers."""
    if not (os.environ.get("AWS_BEARER_TOKEN_BEDROCK") or os.environ.get("AWS_ACCESS_KEY_ID")):
        return False
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        return False
    try:
        boto3.client("bedrock-runtime", region_name=settings.aws_region).converse(
            modelId=os.environ.get("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL),
            messages=[{"role": "user", "content": [{"text": "ok"}]}],
            inferenceConfig={"maxTokens": 5, "temperature": 0},
        )
    except (ClientError, BotoCoreError):
        return False
    return True


def _mantle_available(settings: Settings) -> bool:
    """Bedrock Projects endpoint; counts as available only if a model answers."""
    token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "")
    if not token:
        return False
    import json
    import urllib.error
    import urllib.request

    url = MANTLE_BASE_URL.format(region=settings.aws_region) + "/chat/completions"
    body = json.dumps({
        "model": os.environ.get("MANTLE_MODEL_ID", DEFAULT_MANTLE_MODEL),
        "messages": [{"role": "user", "content": "ok"}],
        "max_tokens": 5,
    }).encode()
    request = urllib.request.Request(
        url, data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20):
            return True
    except Exception:  # noqa: BLE001 - any failure means "not usable"
        return False


def _ollama_available(settings: Settings) -> bool:
    try:
        import urllib.request

        with urllib.request.urlopen(f"{settings.ollama_host}/api/tags", timeout=2):
            return True
    except Exception:  # noqa: BLE001 - any failure means "not usable"
        return False


def detect_provider(settings: Settings | None = None) -> str:
    settings = settings or Settings.from_env()
    forced = os.environ.get("ACREVOICE_MODEL_PROVIDER", "").strip().lower()
    if forced:
        return forced
    if _mantle_available(settings):
        return "mantle"
    if _bedrock_available(settings):
        return "bedrock"
    if _ollama_available(settings):
        return "ollama"
    if settings.anthropic_api_key:
        return "anthropic"
    return "none"


def build_model(provider: str, settings: Settings | None = None):
    """Return a Strands model for the provider, or None for the deterministic policy."""
    settings = settings or Settings.from_env()
    if provider == "mantle":
        from strands.models.openai import OpenAIModel

        return OpenAIModel(
            client_args={
                "api_key": os.environ["AWS_BEARER_TOKEN_BEDROCK"],
                "base_url": MANTLE_BASE_URL.format(region=settings.aws_region),
            },
            model_id=os.environ.get("MANTLE_MODEL_ID", DEFAULT_MANTLE_MODEL),
            params={"temperature": 0, "max_tokens": 1024},
        )
    if provider == "bedrock":
        from strands.models import BedrockModel

        return BedrockModel(
            model_id=os.environ.get("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL),
            region_name=settings.aws_region,
            temperature=0,
        )
    if provider == "ollama":
        from strands.models.ollama import OllamaModel

        return OllamaModel(
            host=settings.ollama_host,
            model_id=os.environ.get("OLLAMA_MODEL_ID", DEFAULT_OLLAMA_MODEL),
            temperature=0,
        )
    if provider == "anthropic":
        from strands.models.anthropic import AnthropicModel

        return AnthropicModel(
            client_args={"api_key": settings.anthropic_api_key},
            model_id=os.environ.get("ANTHROPIC_MODEL_ID", DEFAULT_ANTHROPIC_MODEL),
            max_tokens=1024,
            params={"temperature": 0},
        )
    return None
