"""Verify CALL-E and AWS credentials without printing or burning anything.

Run:  ./.venv/bin/python scripts/check_credentials.py

Checks are read-only: no phone call is placed and no secret value is ever printed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def credential_status(secret: str) -> str:
    """Confirm that a credential loaded without exposing any of its value."""
    return f"present ({len(secret)} chars)"


def check_calle() -> bool:
    key = os.environ.get("CALLE_API_KEY", "").strip()
    if not key:
        print("  FAIL  CALLE_API_KEY is not set (add it to .env)")
        return False
    print(f"  key   {credential_status(key)}")
    try:
        from calle import CalleClient
    except ImportError:
        print("  FAIL  calle-ai not installed: ./.venv/bin/pip install calle-ai")
        return False

    client = CalleClient(api_key=key)
    try:
        client.goals.list()  # read-only; does NOT consume a call
    except Exception as exc:  # noqa: BLE001 - surface the provider's own message
        name = type(exc).__name__
        if "Auth" in name:
            print(f"  FAIL  key rejected by CALL-E ({name})")
            return False
        print(f"  WARN  reached CALL-E but got {name}: {exc}")
        print("        (auth may still be fine - check the dashboard)")
        return True
    print("  OK    CALL-E key accepted, 0 calls consumed")
    return True


def check_aws() -> bool:
    region = os.environ.get("AWS_REGION", "eu-central-1")
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError:
        print("  FAIL  boto3 not installed")
        return False

    try:
        identity = boto3.client("sts", region_name=region).get_caller_identity()
    except (BotoCoreError, ClientError) as exc:
        print(f"  FAIL  no usable AWS credentials ({type(exc).__name__})")
        print("        run:  aws configure")
        return False
    print(f"  OK    AWS credentials valid (account ...{identity['Account'][-4:]}, region {region})")

    try:
        models = boto3.client("bedrock", region_name=region).list_foundation_models()
    except (BotoCoreError, ClientError) as exc:
        print(f"  FAIL  Bedrock not reachable in {region} ({type(exc).__name__})")
        print("        enable model access in the Bedrock console, or try another region")
        return False

    summaries = models.get("modelSummaries", [])
    wanted = ("claude", "nova", "llama", "mistral", "qwen", "deepseek")
    by_provider: dict[str, list[str]] = {}
    for m in summaries:
        mid = m["modelId"]
        if "TEXT" not in m.get("outputModalities", ["TEXT"]):
            continue
        for w in wanted:
            if w in mid.lower():
                by_provider.setdefault(w, []).append(mid)
                break

    if not by_provider:
        print(f"  FAIL  no usable text models in {region} - request model access in the Bedrock console")
        return False

    print(f"  OK    Bedrock reachable in {region}, {len(summaries)} models listed")
    for prov in wanted:
        ids = by_provider.get(prov, [])
        if ids:
            print(f"        {prov:9s} {len(ids):3d}  e.g. {ids[0]}")
    if "claude" not in by_provider and "nova" not in by_provider:
        print("  WARN  neither Claude nor Nova available - enable model access in the Bedrock console")
    return True


def main() -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    print("CALL-E")
    calle_ok = check_calle()
    print("\nAWS Bedrock")
    aws_ok = check_aws()

    print()
    if calle_ok and aws_ok:
        print("All credentials ready.")
        return 0
    print("Some checks failed - see above. The demo still runs without them:")
    print("  ./.venv/bin/python -m acrevoice")
    return 1


if __name__ == "__main__":
    sys.exit(main())
