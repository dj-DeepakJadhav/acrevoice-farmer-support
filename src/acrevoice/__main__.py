"""Local demo entry point.

    python -m acrevoice            run the end-to-end demo with the local provider
    python -m acrevoice --live     place a real CALL-E call (uses one of your calls)
    python -m acrevoice web        start the adviser console
"""

from __future__ import annotations

import json
import sys

from .call_adapter import build_call_provider
from .config import Settings
from .sample_case import ANSWERS, QUESTIONS, RECORD, SCHEME_CODE
from .store import AuditStore
from .workflow import export_correction_package, import_case, review_case, run_call


def run_demo(*, live: bool = False, language: str = "de") -> dict:
    settings = Settings.from_env()
    store = AuditStore("acrevoice.db")

    case_id = import_case(store, record=dict(RECORD), scheme_code=SCHEME_CODE,
                          questions=QUESTIONS, language=language)

    if live:
        if not settings.has_calle:
            raise SystemExit("CALLE_API_KEY is not set; add it to .env")
        if not settings.demo_phone_number:
            raise SystemExit("DEMO_PHONE_NUMBER is not set; add it to .env")
        provider = build_call_provider("call-e", api_key=settings.calle_api_key)
        phone = settings.demo_phone_number
        print(f"Placing a REAL call to {phone} in {language}...")
    else:
        provider = build_call_provider("demo", answers=ANSWERS)
        phone = "+49000000000"

    outcome = run_call(store, case_id=case_id, provider=provider, farmer_name="Anna Bauer",
                       phone=phone, questions=QUESTIONS)
    print(f"call outcome: {outcome.outcome}")

    confirmed = {a.field for a in outcome.answers if a.confirmed}
    review = review_case(store, case_id=case_id, approved_fields=confirmed,
                         reviewer="Demo adviser", notes="Confirmed with farmer")
    package = export_correction_package(store, case_id, review)
    store.close()
    return package


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "web":
        from .server import main as web_main

        web_main()
        return
    language = "en" if "--en" in args else "de"
    package = run_demo(live="--live" in args, language=language)
    print(json.dumps(package, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
