"""Test-session guardrails.

Real model calls (Bedrock, Mantle, Ollama, Anthropic) in the test suite are
forbidden: they are slow, non-deterministic, and - for the paid providers -
cost real money.  ``ACREVOICE_MODEL_PROVIDER=none`` short-circuits
``detect_provider`` before it probes any of them, so ``build_record_agent()``
always returns the deterministic ``RecordAgent``.  Individual tests that need
to exercise ``StrandsRecordAgent`` behaviour should inject a stub via
``run_call(..., record_agent=...)`` instead of relying on a real model.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _no_real_model_provider() -> None:
    os.environ["ACREVOICE_MODEL_PROVIDER"] = "none"
