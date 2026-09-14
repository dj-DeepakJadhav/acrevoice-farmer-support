"""The Strands agent.

The agent's job is deliberately narrow: decide which missing field to ask about
next, and turn a farmer's spoken answer into a value an adviser can check.  It
does not decide eligibility and it never approves anything.

Spoken answers are why this needs a model rather than a regex.  A farmer says
"zweiundvierzig Komma fünf", "ca. 42,5 Hektar" or "knapp 43" - all of which mean
roughly the same number, and one of which should be flagged as approximate.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from strands import Agent, tool

from .config import Settings, build_model, detect_provider

SYSTEM_PROMPT = """You support an agricultural adviser completing a farmer's area-aid application.

Your only responsibilities:
1. Decide which missing field to ask about next.
2. Normalise a farmer's spoken answer into a clean value.
3. Flag anything implausible or approximate so a human checks it.

Rules you must not break:
- Never decide eligibility, subsidy amounts, or approval.
- Never invent a value. If an answer is unclear, return "unknown".
- An approximate answer ("about 43", "knapp 43") is not the same as an exact one.
  Normalise it, but set approximate=true.
- Answers may be in German or English.

Always use the provided tools rather than answering from memory."""


@dataclass(frozen=True)
class MissingField:
    name: str
    question: str


@tool
def normalise_area(spoken: str) -> str:
    """Normalise a spoken land-area answer into hectares.

    Args:
        spoken: what the farmer said, e.g. "zweiundvierzig Komma fünf" or "about 43 ha".

    Returns:
        JSON with keys: value (string number or "unknown"), approximate (bool), note.
    """
    text = (spoken or "").strip().lower()
    approximate = any(w in text for w in ("ca.", "circa", "etwa", "knapp", "about", "around", "~"))
    cleaned = text.replace(",", ".")
    number = ""
    current = ""
    for ch in cleaned:
        if ch.isdigit() or (ch == "." and current):
            current += ch
        elif current:
            number = number or current
            current = ""
    number = number or current
    if not number:
        return json.dumps({"value": "unknown", "approximate": False,
                           "note": "no number found; the model should spell out the digits"})
    try:
        value = float(number)
    except ValueError:
        return json.dumps({"value": "unknown", "approximate": False, "note": "unparseable"})
    if not 0 < value <= 10000:
        return json.dumps({"value": "unknown", "approximate": approximate,
                           "note": f"{value} ha is outside a plausible parcel size"})
    return json.dumps({"value": f"{value:g}", "approximate": approximate, "note": ""})


@tool
def normalise_yes_no(spoken: str) -> str:
    """Normalise a spoken yes/no answer in German or English.

    Args:
        spoken: what the farmer said, e.g. "ja", "nein", "yes", "I think so".

    Returns:
        JSON with keys: value ("yes", "no" or "unknown") and note.
    """
    text = (spoken or "").strip().lower()
    if any(w in text for w in ("vielleicht", "glaube", "denke", "maybe", "think", "not sure")):
        return json.dumps({"value": "unknown", "note": "hedged answer; ask again"})
    if any(text.startswith(w) or f" {w}" in text for w in ("ja", "jawohl", "yes", "yep", "genau")):
        return json.dumps({"value": "yes", "note": ""})
    if any(text.startswith(w) or f" {w}" in text for w in ("nein", "ne", "no", "nope")):
        return json.dumps({"value": "no", "note": ""})
    return json.dumps({"value": "unknown", "note": "not a clear yes or no"})


# Words that mark an answer as hedged rather than stated - checked here too,
# not just in the Strands tools, because RecordAgent (not StrandsRecordAgent)
# is what actually runs whenever no model provider is reachable.
HEDGE_WORDS = (
    "vielleicht", "glaube", "glaub", "denk", "könnte", "vermutlich", "eigentlich",
    "maybe", "guess", "suppose", "think", "probably", "possibly", "not sure", "keine ahnung",
    "weiß nicht", "weiss nicht", "don't know", "do not know",
)

APPROXIMATE_WORDS = ("ca.", "circa", "etwa", "knapp", "ungefähr", "ungefaehr", "about", "around", "roughly", "approximately", "~")


class RecordAgent:
    """Deterministic policy; always available, used when no model provider is."""

    def find_missing(self, record: dict[str, str], questions: dict[str, str]) -> list[MissingField]:
        return [MissingField(name, q) for name, q in questions.items()
                if not (record.get(name) or "").strip()]

    def normalise(self, *, field: str, spoken: str) -> dict:
        """No model available: the spoken text is used as-is, except a hedge word
        still forces "unknown" so a provider's confirmed=True can be downgraded
        (see workflow.run_call) even without a model to catch it."""
        text = (spoken or "").strip().lower()
        if any(word in text for word in HEDGE_WORDS):
            return {"value": "unknown", "approximate": False, "note": "hedged answer"}
        approximate = any(word in text for word in APPROXIMATE_WORDS)
        value = spoken
        if field.endswith("_ha") or field in ("leguminosen_anteil", "rgv_je_hektar"):
            numbers = re.findall(r"-?\d+(?:[.,]\d+)?", text)
            if len(numbers) == 1:
                value = numbers[0].replace(",", ".")
                if float(value) < 0:
                    value = "unknown"
            else:
                value = "unknown"
        return {"value": value, "approximate": approximate, "note": ""}


class StrandsRecordAgent(RecordAgent):
    """Strands agent that normalises spoken answers before an adviser sees them."""

    def __init__(self, settings: Settings | None = None, provider: str | None = None):
        self.settings = settings or Settings.from_env()
        self.provider = provider or detect_provider(self.settings)
        model = build_model(self.provider, self.settings)
        if model is None:
            raise RuntimeError(f"No model available for provider {self.provider!r}")
        self.agent = Agent(model=model, tools=[normalise_area, normalise_yes_no],
                           system_prompt=SYSTEM_PROMPT)

    def normalise(self, *, field: str, spoken: str) -> dict:
        """Return {'value', 'approximate', 'note'} for one spoken answer."""
        result = self.agent(
            f"The farmer was asked about '{field}' and said: \"{spoken}\".\n"
            "Use the right tool to normalise it, then reply with ONLY the tool's JSON."
        )
        text = str(result).strip()
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        return {"value": "unknown", "approximate": False, "note": f"unparsed agent reply: {text[:80]}"}


def build_record_agent(settings: Settings | None = None) -> RecordAgent:
    """Use the Strands agent when a model is reachable, else the deterministic policy."""
    settings = settings or Settings.from_env()
    provider = detect_provider(settings)
    if provider == "none":
        return RecordAgent()
    try:
        return StrandsRecordAgent(settings, provider)
    except Exception:  # noqa: BLE001 - never let model trouble break the demo
        return RecordAgent()
