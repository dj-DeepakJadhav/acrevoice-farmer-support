"""Real CAP schemes a German farm advisory service actually works with.

Sources (checked September 2026):
  Öko-Regelungen  https://www.stmelf.bayern.de/mam/cms01/agrarpolitik/dateien/merkblatt_oekoregelungen.pdf
  Anpassungen 26  https://www.bmleh.de/SharedDocs/Downloads/DE/_Landwirtschaft/EU-Agrarpolitik-Foerderung/anpassungen-oeko-regelungen-2026.pdf
  Mehrfachantrag  https://www.stmelf.bayern.de/mam/cms01/agrarpolitik/dateien/m_mfa.pdf
  GLÖZ standards  https://www.landwirtschaftskammer.de/foerderung/konditionalitaet/aenderungen.htm

Each scheme carries the question a farmer is actually asked, why the answer matters, and
what is at stake if the field stays blank.  The "why" is not decoration: an adviser has
to justify the call, and a farmer deserves to know why they are being phoned.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field


@dataclass(frozen=True)
class SchemeField:
    """One piece of information a farmer must supply for a scheme."""

    name: str
    label: dict[str, str]
    question: dict[str, str]
    why: dict[str, str]
    kind: str = "text"  # text | number | yes_no | list


@dataclass(frozen=True)
class Scheme:
    """A funding measure or conditionality standard within the Mehrfachantrag."""

    code: str
    name: dict[str, str]
    programme: dict[str, str]
    summary: dict[str, str]
    payment: dict[str, str]
    source: str
    fields: list[SchemeField] = dc_field(default_factory=list)

    def field(self, name: str) -> SchemeField | None:
        return next((f for f in self.fields if f.name == name), None)


SCHEMES: dict[str, Scheme] = {
    "OER2": Scheme(
        code="ÖR2",
        name={"de": "Anbau vielfältiger Kulturen",
              "en": "Growing a diverse range of crops"},
        programme={"de": "Öko-Regelung · Mehrfachantrag", "en": "Eco-scheme · Multiple Application"},
        summary={
            "de": "Mindestens fünf verschiedene Hauptfruchtarten auf dem Ackerland, "
                  "mit Anteilsgrenzen je Kultur und einem Mindestanteil Leguminosen.",
            "en": "At least five different main crop types on arable land, with share "
                  "limits per crop and a minimum share of legumes.",
        },
        payment={"de": "Freiwillige Öko-Regelung; aktuelle Bedingungen durch Beratung prüfen",
                 "en": "Voluntary eco-scheme; adviser checks current conditions"},
        source="https://www.stmelf.bayern.de/mam/cms01/agrarpolitik/dateien/merkblatt_oekoregelungen.pdf",
        fields=[
            SchemeField(
                name="hauptfruchtarten",
                label={"de": "Angebaute Hauptfruchtarten", "en": "Main crop types grown"},
                question={
                    "de": "Welche Hauptfruchtarten haben Sie in diesem Antragsjahr auf Ihrem "
                          "Ackerland angebaut? Bitte nennen Sie alle.",
                    "en": "Which main crop types did you grow on your arable land this "
                          "application year? Please name them all.",
                },
                why={
                    "de": "ÖR2 verlangt mindestens fünf Hauptfruchtarten. Im Antrag sind bisher "
                          "nur vier eindeutig zugeordnet.",
                    "en": "ÖR2 requires at least five main crop types. Only four are clearly "
                          "assigned in the application so far.",
                },
                kind="list",
            ),
            SchemeField(
                name="leguminosen_anteil",
                label={"de": "Anteil Leguminosen", "en": "Share of legumes"},
                question={
                    "de": "Wie viel Prozent Ihres Ackerlands waren in diesem Jahr Leguminosen, "
                          "also zum Beispiel Erbsen, Bohnen, Klee oder Luzerne?",
                    "en": "What percentage of your arable land was legumes this year — for "
                          "example peas, beans, clover or lucerne?",
                },
                why={
                    "de": "ÖR2 setzt einen Mindestanteil Leguminosen voraus. Ohne diese Angabe "
                          "kann die Auszahlung nicht berechnet werden.",
                    "en": "ÖR2 requires a minimum share of legumes. Without this the payment "
                          "cannot be calculated.",
                },
                kind="number",
            ),
        ],
    ),
    "GLOEZ6": Scheme(
        code="GLÖZ 6",
        name={"de": "Mindestbodenbedeckung im Winter",
              "en": "Minimum soil cover in winter"},
        programme={"de": "Konditionalität · Mehrfachantrag", "en": "Conditionality · Multiple Application"},
        summary={
            "de": "Mindestbodenbedeckung auf Ackerland. Zeitraum und Ausnahmen sind durch die Beratung für Fläche und Antragsjahr zu prüfen.",
            "en": "Minimum soil cover on arable land. The adviser verifies the applicable period and exceptions for the parcel and year.",
        },
        payment={"de": "Voraussetzung für alle Direktzahlungen",
                 "en": "Precondition for all direct payments"},
        source="https://www.stmelf.bayern.de/foerderung/agrarpolitik/faq-gloez-konditionalitaet",
        fields=[
            SchemeField(
                name="bodenbedeckung_art",
                label={"de": "Art der Bodenbedeckung", "en": "Type of soil cover"},
                question={
                    "de": "Womit war der Schlag über den Winter bedeckt? Zum Beispiel "
                          "Zwischenfrucht, Untersaat, Stoppeln oder Mulch.",
                    "en": "What covered this parcel over the winter? For example a cover "
                          "crop, undersowing, stubble or mulch.",
                },
                why={
                    "de": "Die Beratung benötigt die Art der Bedeckung zur Prüfung. Eine fehlende Angabe ist noch kein festgestellter Verstoß.",
                    "en": "The adviser needs the cover type to review the record. A missing value does not establish non-compliance.",
                },
            ),
            SchemeField(
                name="bedeckung_zeitraum_eingehalten",
                label={"de": "Zeitraum eingehalten", "en": "Period observed"},
                question={
                    "de": "Blieb die Bedeckung im gesamten Zeitraum bestehen, den Sie mit Ihrer Beratung für diese Fläche vereinbart haben? Falls unbekannt, sagen Sie bitte unklar.",
                    "en": "Did the cover remain throughout the period agreed with your adviser for this parcel? If you do not know that period, please say unclear.",
                },
                why={
                    "de": "Der passende Zeitraum wird von der Beratung geprüft, nicht vom Telefonagenten festgelegt.",
                    "en": "The adviser verifies the applicable period; the phone agent does not determine it.",
                },
                kind="yes_no",
            ),
        ],
    ),
    "GLOEZ8": Scheme(
        code="GLÖZ 8",
        name={"de": "Landschaftselemente und Flächeninventar", "en": "Landscape features and parcel inventory"},
        programme={"de": "Konditionalität · Mehrfachantrag", "en": "Conditionality · Multiple Application"},
        summary={
            "de": "GLÖZ 8 schützt Landschaftselemente. Die frühere 4-%-Brachepflicht ist seit 2025 entfallen. Brache wird hier nur als ergänzendes Flächeninventar erfasst.",
            "en": "GLÖZ 8 protects landscape features. The former 4% fallow obligation was removed in 2025. Fallow area here is supplementary parcel inventory only.",
        },
        payment={"de": "Voraussetzung für alle Direktzahlungen",
                 "en": "Precondition for all direct payments"},
        source="https://www.landwirtschaftskammer.de/foerderung/hinweise/agrarreform.htm",
        fields=[
            SchemeField(
                name="brache_ha",
                label={"de": "Brachefläche", "en": "Fallow area"},
                question={
                    "de": "Wie viele Hektar Ihres Ackerlands lagen in diesem Jahr brach, "
                          "also ohne Ernte und ohne Nutzung?",
                    "en": "How many hectares of your arable land lay fallow this year — "
                          "without harvest and without use?",
                },
                why={
                    "de": "Ergänzende Angabe zum Flächeninventar; keine GLÖZ-8-Mindestbrachepflicht.",
                    "en": "Supplementary parcel inventory; not a GLÖZ 8 minimum-fallow requirement.",
                },
                kind="number",
            ),
            SchemeField(
                name="landschaftselemente",
                label={"de": "Landschaftselemente", "en": "Landscape features"},
                question={
                    "de": "Gibt es auf Ihren Ackerflächen Landschaftselemente wie Hecken, "
                          "Feldgehölze, Baumreihen oder Feldraine?",
                    "en": "Are there landscape features on your arable land such as hedges, "
                          "copses, tree rows or field margins?",
                },
                why={
                    "de": "Vorhandene Landschaftselemente müssen für die Beratung dokumentiert werden; ihre Erhaltung ist weiterhin relevant.",
                    "en": "Document existing landscape features for the adviser; their preservation remains relevant.",
                },
                kind="yes_no",
            ),
        ],
    ),
    "OER4": Scheme(
        code="ÖR4",
        name={"de": "Extensivierung des Dauergrünlands",
              "en": "Extensive management of permanent grassland"},
        programme={"de": "Öko-Regelung · Mehrfachantrag", "en": "Eco-scheme · Multiple Application"},
        summary={
            "de": "Das gesamte Dauergrünland des Betriebs wird extensiv bewirtschaftet, "
                  "begrenzt über den Viehbesatz je Hektar.",
            "en": "The holding's entire permanent grassland is managed extensively, limited "
                  "by livestock units per hectare.",
        },
        payment={"de": "je Hektar Dauergrünland", "en": "per hectare of permanent grassland"},
        source="https://www.stmelf.bayern.de/mam/cms01/agrarpolitik/dateien/merkblatt_oekoregelungen.pdf",
        fields=[
            SchemeField(
                name="rgv_je_hektar",
                label={"de": "Viehbesatz (RGV je Hektar)", "en": "Livestock density (LU per hectare)"},
                question={
                    "de": "Wie viele raufutterfressende Großvieheinheiten je Hektar "
                          "Dauergrünland hielten Sie im Durchschnitt des Jahres?",
                    "en": "How many roughage-consuming livestock units per hectare of "
                          "permanent grassland did you keep on average over the year?",
                },
                why={
                    "de": "ÖR4 gilt nur innerhalb fester Ober- und Untergrenzen des "
                          "Viehbesatzes. Ohne diesen Wert ist die Prüfung nicht möglich.",
                    "en": "ÖR4 applies only within fixed upper and lower livestock density "
                          "limits. Without this figure the check cannot be made.",
                },
                kind="number",
            ),
        ],
    ),
    "OER1B": Scheme(
        code="ÖR1b",
        name={"de": "Bewirtschaftung von Blühflächen und -streifen",
              "en": "Managing flower strips and areas"},
        programme={"de": "Öko-Regelung · Mehrfachantrag", "en": "Eco-scheme · Multiple Application"},
        summary={
            "de": "Ein- oder mehrjährige Blühflächen und -streifen aus einer zugelassenen "
                  "Saatgutmischung, mit einer Höchstgrenze je Schlag.",
            "en": "Annual or multi-year flower strips and areas from an approved seed mix, "
                  "capped per parcel.",
        },
        payment={"de": "Freiwillige Öko-Regelung; keine Zahlungsberechnung in AcreVoice",
                 "en": "Voluntary eco-scheme; AcreVoice does not calculate payments"},
        source="https://www.stmelf.bayern.de/mam/cms01/agrarpolitik/dateien/merkblatt_oekoregelungen.pdf",
        fields=[
            SchemeField(
                name="bluehmischung_art",
                label={"de": "Art der Blühmischung", "en": "Type of flower mix"},
                question={
                    "de": "Welche Saatgutmischung haben Sie für die Blühfläche verwendet?",
                    "en": "Which seed mix did you use for the flower strip?",
                },
                why={
                    "de": "ÖR1b ist nur für zugelassene Blühmischungen förderfähig. Ohne diese "
                          "Angabe kann die Fläche nicht anerkannt werden.",
                    "en": "ÖR1b only supports approved flower mixes. Without this the area "
                          "cannot be recognised.",
                },
            ),
            SchemeField(
                name="flaeche_ha",
                label={"de": "Blühfläche in Hektar", "en": "Flower strip area in hectares"},
                question={
                    "de": "Wie viele Hektar haben Sie mit dieser Blühmischung angelegt?",
                    "en": "How many hectares did you plant with this flower mix?",
                },
                why={
                    "de": "Die Auszahlung von ÖR1b richtet sich nach der Hektarzahl der "
                          "Blühfläche. Ohne diesen Wert kann sie nicht berechnet werden.",
                    "en": "ÖR1b's payment depends on the hectares of flower strip. Without "
                          "this figure it cannot be calculated.",
                },
                kind="number",
            ),
        ],
    ),
}


def get_scheme(code: str) -> Scheme:
    if code not in SCHEMES:
        raise ValueError(f"Unknown scheme {code!r}; known: {sorted(SCHEMES)}")
    return SCHEMES[code]


def questions_for(code: str, language: str) -> dict[str, str]:
    """The farmer-facing question per field, for the workflow's questions mapping."""
    return {f.name: f.question[language] for f in get_scheme(code).fields}


def labels_for(code: str, language: str) -> dict[str, str]:
    return {f.name: f.label[language] for f in get_scheme(code).fields}
