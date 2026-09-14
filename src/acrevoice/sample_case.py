"""Synthetic GAP-style case queue used by the local demo and the adviser console.

Every case is a real CAP scheme (``schemes.py``) applied to a fictitious Bavarian
holding.  Names, parcel IDs and figures are made up but shaped like the real thing,
so the console demo looks like an adviser's actual queue rather than a toy example.
"""

from __future__ import annotations

from . import schemes
from .store import AuditStore
from .workflow import import_case

# -- holdings ------------------------------------------------------------------

HOLDINGS = {
    "DE-BY-MUELLER-01": "Hof Müller",
    "DE-BY-MAYR-02": "Mayr Hof",
    "DE-BY-GRUBER-03": "Gruber Landwirtschaft",
    "DE-BY-KASTNER-04": "Kastner Blühwiesenhof",
}

# -- cases -----------------------------------------------------------------
# Each entry is a full, self-contained case: which scheme it belongs to, the
# original record (missing fields left as "") and the language to call in.
# Missing-field counts, holdings and schemes are deliberately varied so the
# queue looks like a real adviser's morning, not a single repeated example.

CASES: list[dict] = [
    {
        "scheme_code": "OER2",
        "language": "de",
        "record": {
            "holding_id": "DE-BY-MUELLER-01",
            "holding_name": HOLDINGS["DE-BY-MUELLER-01"],
            "application_year": "2026",
            "parcel_id": "BY-4821-07",
            "hauptfruchtarten": "",
            "leguminosen_anteil": "12",
        },
    },
    {
        "scheme_code": "GLOEZ6",
        "language": "de",
        "record": {
            "holding_id": "DE-BY-MUELLER-01",
            "holding_name": HOLDINGS["DE-BY-MUELLER-01"],
            "application_year": "2026",
            "parcel_id": "BY-4821-11",
            "bodenbedeckung_art": "",
            "bedeckung_zeitraum_eingehalten": "",
        },
    },
    {
        "scheme_code": "OER4",
        "language": "de",
        "record": {
            "holding_id": "DE-BY-MAYR-02",
            "holding_name": HOLDINGS["DE-BY-MAYR-02"],
            "application_year": "2026",
            "parcel_id": "BY-2290-02",
            "rgv_je_hektar": "",
        },
    },
    {
        "scheme_code": "GLOEZ8",
        "language": "de",
        "record": {
            "holding_id": "DE-BY-MAYR-02",
            "holding_name": HOLDINGS["DE-BY-MAYR-02"],
            "application_year": "2025",
            "parcel_id": "BY-2290-15",
            "brache_ha": "3.4",
            "landschaftselemente": "",
        },
    },
    {
        "scheme_code": "OER2",
        "language": "de",
        "record": {
            "holding_id": "DE-BY-GRUBER-03",
            "holding_name": HOLDINGS["DE-BY-GRUBER-03"],
            "application_year": "2026",
            "parcel_id": "BY-5533-09",
            "hauptfruchtarten": "",
            "leguminosen_anteil": "",
        },
    },
    {
        "scheme_code": "GLOEZ8",
        "language": "de",
        "record": {
            "holding_id": "DE-BY-GRUBER-03",
            "holding_name": HOLDINGS["DE-BY-GRUBER-03"],
            "application_year": "2026",
            "parcel_id": "BY-5533-22",
            "brache_ha": "",
            "landschaftselemente": "ja",
        },
    },
    {
        "scheme_code": "OER1B",
        "language": "de",
        "record": {
            "holding_id": "DE-BY-KASTNER-04",
            "holding_name": HOLDINGS["DE-BY-KASTNER-04"],
            "application_year": "2026",
            "parcel_id": "BY-6014-03",
            "bluehmischung_art": "",
            "flaeche_ha": "1.4",
        },
    },
]

# Plausible answer per scheme field, shared by every case that is missing it.
# Field names are unique across all four schemes, so one flat table covers the
# whole queue; a `DemoCallProvider` only reads the entries for the fields it
# was actually asked about.
ANSWERS_BY_FIELD: dict[str, str] = {
    "hauptfruchtarten": "Winterweizen, Wintergerste, Raps, Mais, Ackerbohnen",
    "leguminosen_anteil": "9",
    "bodenbedeckung_art": "Zwischenfrucht aus Senf und Phacelia",
    "bedeckung_zeitraum_eingehalten": "ja",
    "rgv_je_hektar": "1.1",
    "brache_ha": "2.6",
    "landschaftselemente": "ja",
    "bluehmischung_art": "Bayerische Regio-Mischung mit Malve und Ringelblume",
}


def questions_for_case(case: dict) -> dict[str, str]:
    return schemes.questions_for(case["scheme_code"], case["language"])


def seed_queue(store: AuditStore) -> list[str]:
    """Import every sample case; used to populate an empty console on first use."""
    return [
        import_case(
            store,
            record=dict(case["record"]),
            scheme_code=case["scheme_code"],
            questions=questions_for_case(case),
            language=case["language"],
        )
        for case in CASES
    ]


# -- backwards-compatible single-case demo, for ``python -m acrevoice`` --------
# The CLI demo only ever runs one case at a time; it uses the first queue entry.

_DEFAULT_CASE = CASES[0]
RECORD = dict(_DEFAULT_CASE["record"])
SCHEME_CODE = _DEFAULT_CASE["scheme_code"]
QUESTIONS = questions_for_case(_DEFAULT_CASE)
ANSWERS = dict(ANSWERS_BY_FIELD)
