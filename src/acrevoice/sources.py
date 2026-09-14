"""Small, reviewed catalogue of official sources for the Förderlotse demo.

The catalogue deliberately describes a possible starting point, never an
eligibility decision.  It is versioned in code so every recommendation shows
the publisher, URL and the date it was last checked.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SourceCard:
    source_id: str
    land: str
    topic: str
    title: dict[str, str]
    publisher: str
    publisher_en: str
    url: str
    scope: dict[str, str]
    document_date: str
    record_type: dict[str, str]
    checked_at: str
    review_by: str
    required_facts: tuple[str, ...]

    def view(self, language: str) -> dict:
        result = asdict(self)
        result["title"] = self.title[language]
        result["scope"] = self.scope[language]
        result["publisher_display"] = (f"{self.publisher} ({self.publisher_en})"
                                       if language == "en" else self.publisher)
        result["required_facts"] = list(self.required_facts)
        result["record_type"] = self.record_type[language]
        result["guidance"] = (
            "Möglicher Anhaltspunkt, keine Förderzusage. Eine Beratung prüft Betrieb, Flächen und Antragsjahr."
            if language == "de" else
            "Possible starting point, not an eligibility decision. An adviser verifies the holding, parcels and application year."
        )
        return result


CATALOGUE = (
    SourceCard(
        source_id="bayern-oeko-regelungen-2025", land="Bayern", topic="eco_scheme",
        title={"de": "Öko-Regelungen: Merkblatt 2025", "en": "Eco-schemes: 2025 guidance note"},
        publisher="Bayerisches Staatsministerium für Ernährung, Landwirtschaft, Forsten und Tourismus",
        publisher_en="Bavarian State Ministry for Food, Agriculture, Forestry and Tourism",
        url="https://www.stmelf.bayern.de/mam/cms01/agrarpolitik/dateien/merkblatt_oekoregelungen.pdf",
        scope={"de": "Offizielle Bayerische Hinweise zu Öko-Regelungen im Mehrfachantrag.",
               "en": "Official Bavarian guidance on eco-schemes in the Multiple Application."},
        document_date="2025", record_type={"de": "Öffentliche Programmregel", "en": "Official public programme rule"},
        checked_at="2026-09-14", review_by="2026-12-31",
        required_facts=("Antragsjahr", "Kulturen oder Maßnahme", "betroffene Flächen"),
    ),
    SourceCard(
        source_id="bayern-mehrfachantrag-2025", land="Bayern", topic="multiple_application",
        title={"de": "Mehrfachantrag: Merkblatt 2025", "en": "Multiple Application: 2025 guidance note"},
        publisher="Bayerisches Staatsministerium für Ernährung, Landwirtschaft, Forsten und Tourismus",
        publisher_en="Bavarian State Ministry for Food, Agriculture, Forestry and Tourism",
        url="https://www.stmelf.bayern.de/mam/cms01/agrarpolitik/dateien/m_mfa.pdf",
        scope={"de": "Offizielle Informationen zum bayerischen Mehrfachantrag.",
               "en": "Official information on the Bavarian Multiple Application."},
        document_date="2025", record_type={"de": "Öffentliche Antragsleitlinie", "en": "Official public application guidance"},
        checked_at="2026-09-14", review_by="2026-12-31",
        required_facts=("Antragsjahr", "Betriebsnummer", "offene Frage"),
    ),
    SourceCard(
        source_id="bayern-funding-guide-eco", land="Bayern", topic="eco_scheme",
        title={"de": "Förderwegweiser Bayern", "en": "Bavaria funding guide"},
        publisher="Bayerisches Staatsministerium für Ernährung, Landwirtschaft, Forsten und Tourismus",
        publisher_en="Bavarian State Ministry for Food, Agriculture, Forestry and Tourism",
        url="https://www.stmelf.bayern.de/foerderung",
        scope={"de": "Offizieller Überblick über Förderprogramme und zuständige Beratungsstellen.",
               "en": "Official overview of funding programmes and responsible advisory offices."},
        document_date="Current web guidance", record_type={"de": "Öffentlicher Programmindex", "en": "Official public programme index"},
        checked_at="2026-09-14", review_by="2026-12-31",
        required_facts=("Betriebsland", "Förderthema", "Antragsjahr"),
    ),
    SourceCard(
        source_id="bayern-funding-guide-mfa", land="Bayern", topic="multiple_application",
        title={"de": "Förderwegweiser Bayern", "en": "Bavaria funding guide"},
        publisher="Bayerisches Staatsministerium für Ernährung, Landwirtschaft, Forsten und Tourismus",
        publisher_en="Bavarian State Ministry for Food, Agriculture, Forestry and Tourism",
        url="https://www.stmelf.bayern.de/foerderung",
        scope={"de": "Offizieller Überblick über Förderprogramme und zuständige Beratungsstellen.",
               "en": "Official overview of funding programmes and responsible advisory offices."},
        document_date="Current web guidance", record_type={"de": "Öffentlicher Programmindex", "en": "Official public programme index"},
        checked_at="2026-09-14", review_by="2026-12-31",
        required_facts=("Betriebsland", "Förderthema", "Antragsjahr"),
    ),
)


def match_sources(*, land: str, topic: str, language: str) -> list[dict]:
    """Return dated official sources for the selected Bavaria-first slice."""
    if land != "Bayern":
        return []
    return [card.view(language) for card in CATALOGUE if card.topic == topic]
