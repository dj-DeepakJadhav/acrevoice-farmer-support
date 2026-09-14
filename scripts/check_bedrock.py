"""Retest Bedrock after fixing account billing or model access.

Run:  ./.venv/bin/python scripts/check_bedrock.py

Tests plain invocation AND tool calling (which is what the Strands agent actually
needs), then prints the model id to use.  Costs a fraction of a cent per model.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from acrevoice.config import load_env  # noqa: E402

load_env()

import os  # noqa: E402

import boto3  # noqa: E402
from botocore.exceptions import BotoCoreError, ClientError  # noqa: E402

TOOL_CONFIG = {
    "tools": [
        {
            "toolSpec": {
                "name": "record_answer",
                "description": "Record a farmer's answer to a missing application field.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "value": {"type": "string"},
                            "confirmed": {"type": "boolean"},
                        },
                        "required": ["field", "value", "confirmed"],
                    }
                },
            }
        }
    ]
}

# Preference order: cheap and reliable at tool calling first.
CANDIDATES = [
    ("eu-central-1", "eu.anthropic.claude-haiku-4-5-20251001-v1:0"),
    ("eu-central-1", "anthropic.claude-haiku-4-5-20251001-v1:0"),
    ("eu-central-1", "eu.amazon.nova-lite-v1:0"),
    ("eu-central-1", "amazon.nova-lite-v1:0"),
    ("eu-central-1", "qwen.qwen3-32b-v1:0"),
    ("eu-central-1", "zai.glm-4.7-flash"),
    ("us-east-1", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
    ("us-east-1", "us.amazon.nova-lite-v1:0"),
]

PROMPT = (
    "The farmer said 42.5 hectares and confirmed it was correct. "
    "Record the answer for field area_ha."
)


def probe(region: str, model_id: str) -> tuple[bool, bool, str]:
    """Return (invoked, tool_called, note)."""
    rt = boto3.client("bedrock-runtime", region_name=region)
    try:
        rt.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": "Say OK"}]}],
            inferenceConfig={"maxTokens": 10, "temperature": 0},
        )
    except (ClientError, BotoCoreError) as exc:
        msg = getattr(exc, "response", {}).get("Error", {}).get("Message", str(exc))
        return False, False, msg[:70]

    try:
        resp = rt.converse(
            modelId=model_id,
            toolConfig=TOOL_CONFIG,
            messages=[{"role": "user", "content": [{"text": PROMPT}]}],
            inferenceConfig={"maxTokens": 400, "temperature": 0},
        )
        uses = [c["toolUse"] for c in resp["output"]["message"]["content"] if "toolUse" in c]
        if uses:
            return True, True, str(uses[0]["input"])[:60]
        return True, False, "model answered but emitted no tool call"
    except (ClientError, BotoCoreError) as exc:
        msg = getattr(exc, "response", {}).get("Error", {}).get("Message", str(exc))
        return True, False, f"tool call failed: {msg[:50]}"


def main() -> int:
    if not (os.environ.get("AWS_BEARER_TOKEN_BEDROCK") or os.environ.get("AWS_ACCESS_KEY_ID")):
        print("No Bedrock credentials found in .env or environment.")
        return 1

    winner = None
    for region, model_id in CANDIDATES:
        invoked, tooled, note = probe(region, model_id)
        mark = "TOOLS OK" if tooled else ("invokes" if invoked else "blocked ")
        print(f"  {mark}  {region:13s} {model_id}")
        print(f"            {note}")
        if tooled and winner is None:
            winner = (region, model_id)

    print()
    if winner is None:
        print("Bedrock still blocked. The demo runs without it:")
        print("  ACREVOICE_MODEL_PROVIDER=none ./.venv/bin/python -m acrevoice")
        return 1

    region, model_id = winner
    print(f"USE THIS MODEL: {model_id}  (region {region})")
    print("Add to .env:")
    print(f"  AWS_REGION={region}")
    print(f"  BEDROCK_MODEL_ID={model_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
