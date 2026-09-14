"""All human-facing text, in German and English.

Two independent settings, because they answer different questions:

* **call language**    - what the farmer hears, set per case
* **console language** - what the adviser reads, switched in the header

Neither is a fallback for the other.  A German farmer can be called in German
while an evaluator who speaks no German follows along in an English console.
"""

from __future__ import annotations

from dataclasses import dataclass

SUPPORTED = ("de", "en")

# CALL-E recipient locale/region per language.
CALL_LOCALE = {"de": ("de-DE", "DE"), "en": ("en-US", "US")}


@dataclass(frozen=True)
class Script:
    """Everything the farmer hears, in one language."""

    consent: str
    question: dict[str, str]
    read_back: str
    refused: str
    closing: str


SCRIPTS: dict[str, Script] = {
    "de": Script(
        consent=(
            "Guten Tag, hier ist der digitale Assistent Ihrer Agrarberatung. "
            "In Ihrem Flächenantrag {year} fehlen noch {count} Angaben. "
            "Darf ich Ihnen dazu kurz zwei Fragen stellen? "
            "Das Gespräch dauert etwa zwei Minuten und Sie können jederzeit abbrechen."
        ),
        question={
            "area_ha": (
                "Wie viele Hektar Winterweizen haben Sie auf dem Schlag {parcel_id} bewirtschaftet?"
            ),
            "cover_crop_used": (
                "Haben Sie vor dem Winterweizen auf diesem Schlag eine Zwischenfrucht angebaut? "
                "Bitte antworten Sie mit ja oder nein."
            ),
        },
        read_back=(
            "Ich habe notiert: {value}. Ist das richtig? Bitte bestätigen Sie mit ja oder nein."
        ),
        refused="In Ordnung, ich notiere das als offen. Ihre Beratung meldet sich bei Ihnen.",
        closing="Vielen Dank. Ihre Angaben gehen zur Prüfung an Ihre Beratung. Auf Wiederhören.",
    ),
    "en": Script(
        consent=(
            "Hello, this is the digital assistant from your agricultural advisory service. "
            "Your {year} area application is missing {count} details. "
            "May I ask you two short questions? "
            "This takes about two minutes and you can stop at any time."
        ),
        question={
            "area_ha": "How many hectares of winter wheat did you cultivate on parcel {parcel_id}?",
            "cover_crop_used": (
                "Did you plant a cover crop before the winter wheat on this parcel? "
                "Please answer yes or no."
            ),
        },
        read_back="I noted: {value}. Is that correct? Please confirm with yes or no.",
        refused="Understood, I will mark this as open. Your adviser will contact you.",
        closing="Thank you. Your answers go to your adviser for review. Goodbye.",
    ),
}


def get_script(language: str) -> Script:
    if language not in SCRIPTS:
        raise ValueError(f"Unsupported language {language!r}; expected one of {SUPPORTED}")
    return SCRIPTS[language]


def question_for(field: str, language: str, **context: object) -> str:
    """Render one farmer-facing question, falling back to a neutral phrasing."""
    script = get_script(language)
    template = script.question.get(field)
    if template is None:
        label = field.replace("_", " ")
        template = (
            f"Bitte nennen Sie den Wert für {label}."
            if language == "de"
            else f"Please tell me the value for {label}."
        )
    return template.format(**context)


def consent_for(language: str, *, year: str, count: int) -> str:
    return get_script(language).consent.format(year=year, count=count)


def read_back_for(language: str, *, value: str) -> str:
    return get_script(language).read_back.format(value=value)


# --- console strings -------------------------------------------------------
# Keys are stable identifiers; no UI string is hard-coded in either language.

UI: dict[str, dict[str, str]] = {
    "de": {
        "app_name": "AcreVoice",
        "app_role": "Beratungskonsole",
        "title": "Korrekturen zum Flächenantrag",
        "intro": "Fehlende Angaben telefonisch klären und vor der Eingabe ins Portal prüfen.",
        "case": "Fall",
        "holding": "Betrieb",
        "year": "Antragsjahr",
        "console_language": "Sprache der Konsole",
        "call_language": "Sprache des Anrufs",
        "status": "Status",
        "missing_at_import": "Fehlend bei Import",
        "confirmed_by_farmer": "Vom Landwirt bestätigt",
        "start_call": "Anruf starten",
        "call_running": "Anruf läuft …",
        "real_call": "echten Anruf führen",
        "real_call_hint": "Ein echter Anruf verbraucht ein CALL-E-Guthaben.",
        "no_phone_hint": "DEMO_PHONE_NUMBER in .env setzen, um echte Anrufe zu erlauben.",
        "review": "Nachweise prüfen & menschlich freigeben",
        "approve_export": "Ausgewählte freigeben und exportieren",
        "evidence": "Nachweisverlauf",
        "package": "Export für Portal oder Fallakte",
        "no_export": "Nach der menschlichen Freigabe steht hier das Korrekturpaket zum Export bereit.",
        "no_events": "Noch keine Ereignisse.",
        "awaiting_call": "wartet auf Anruf",
        "confirmed": "bestätigt",
        "not_confirmed": "nicht bestätigt",
        "approximate": "ungefähre Angabe",
        "follow_up_warning": "Nicht alle Angaben wurden bestätigt. Unbestätigte Werte werden nie übernommen – der Fall braucht eine Nachfrage.",
        "config_error_warning": "Konfigurationsfehler beim Anruf. Das ist kein Fall für eine Nachfrage beim Landwirt.",
        "live_ready": "echte Anrufe bereit",
        "demo_mode": "Demomodus – keine Telefonnummer hinterlegt",
        "confirm_real_call": "Dies führt einen ECHTEN Anruf und verbraucht ein CALL-E-Guthaben. Fortfahren?",
        "select_one": "Bitte mindestens eine bestätigte Angabe auswählen.",
        "status_needs_information": "Angaben fehlen",
        "status_call_in_progress": "Anruf läuft",
        "status_awaiting_review": "Wartet auf Prüfung",
        "status_needs_follow_up": "Nachfrage nötig",
        "status_closed": "Abgeschlossen",
        "shortcuts_title": "Tastenkürzel",
        "shortcuts_hint": "? für Tastenkürzel",
        "shortcuts_close_hint": "Esc zum Schließen",
        "shortcut_move": "Zwischen Feldern wechseln",
        "shortcut_toggle": "Freigabe umschalten (nur bei bestätigten Angaben)",
        "shortcut_approve": "Ausgewählte freigeben und exportieren",
        "shortcut_call": "Anruf starten",
        "shortcut_help": "Diese Hilfe ein- oder ausblenden",
        "shortcut_escape": "Hilfe schließen",
        "original_value": "Ursprünglicher Wert",
        "proposed_value": "Vorgeschlagener Wert",
        "question_asked": "Gestellte Frage",
        "confirmation_state": "Bestätigungsstatus",
        "timestamp": "Zeitstempel",
        "timeline_col_time": "Zeit",
        "timeline_col_event": "Ereignis",
        "timeline_col_field": "Feld",
        "print_generated": "Ausgedruckt am",
        "scheme_heading": "Fördermaßnahme",
        "at_stake": "Was auf dem Spiel steht",
        "why_heading": "Warum das wichtig ist",
        "note_label": "Technischer Hinweis",
        "spoken_label": "Wortlaut der Antwort",
        "source_label": "Quelle",
        "raw_data": "Rohdaten (für Entwickler)",
        "select_column": "Auswahl",
        "tl_case_imported": "Fall erstellt",
        "tl_missing_fields_identified": "Fehlende Felder erkannt",
        "tl_answer_captured": "Antwort erfasst: {field}",
        "tl_status_changed": "Status: {old} → {new}",
        "tl_reviewed": "Freigegeben durch {reviewer}",
        "tl_call_started": "Anruf gestartet",
        "tl_call_ended": "Anruf beendet: {outcome}",
        "tl_call_failed": "Anruf fehlgeschlagen",
        "tl_call_configuration_error": "Konfigurationsfehler beim Anruf",
        "tl_transcript_recorded": "Gesprächsmitschrift gespeichert",
        "tl_call_language_changed": "Anrufsprache geändert: {language}",
        "tl_unknown_event": "Weiteres Ereignis",
        "outcome_completed": "abgeschlossen",
        "outcome_partial": "teilweise beantwortet",
        "outcome_unreachable": "nicht erreichbar",
        "import_button": "CSV importieren",
        "import_label": "Wählen Sie eine CSV-Datei",
        "import_success": "{count} Fälle importiert",
        "import_error": "Fehler beim Importieren",
        "cases_title": "Fallliste",
        "column_holding": "Betrieb",
        "column_scheme": "Regelung",
        "column_year": "Jahr",
        "column_missing": "Fehlende Felder",
        "column_status": "Status",
        "column_activity": "Aktivität",
        "back_to_list": "Zurück zur Liste",
        "no_cases": "Keine Fälle vorhanden.",
        "empty_cases_message": "Keine Fälle. CSV-Datei hochladen, um zu beginnen.",
        "loading_text": "Wird geladen …",
        "error_upload_failed": "CSV-Upload fehlgeschlagen: {message}",
        "error_unknown_scheme": "Unbekannter Regelungscode in Zeile {row}: {code}",
        "error_call_failed": "Anruf konnte nicht verbunden werden.",
        "error_case_not_found": "Fall nicht gefunden.",
        "activity_just_now": "gerade eben",
        "activity_minutes_ago": "vor {minutes} Min",
        "activity_hours_ago": "vor {hours} Std",
        "activity_yesterday": "gestern",
        "activity_days_ago": "vor {days} Tagen",
        "table_field": "Feld",
        "table_original": "Alter Wert",
        "table_proposed": "Neuer Wert",
        "table_confirmed": "Bestätigt",
        "table_question": "Frage",
        "table_captured": "Erfasst",
        "status_confirmed": "✓ bestätigt",
        "status_unconfirmed": "❌ nicht bestätigt — der Landwirt hat nicht klar geantwortet",
        "status_approximate": "⚠️ ungefähre Angabe — „{value}“",
    },
    "en": {
        "app_name": "AcreVoice",
        "app_role": "adviser console",
        "title": "Area application corrections",
        "intro": "Resolve missing farmer information by phone, then review before it reaches the portal.",
        "case": "Case",
        "holding": "Holding",
        "year": "Application year",
        "console_language": "Console language",
        "call_language": "Call language",
        "status": "Status",
        "missing_at_import": "Missing at import",
        "confirmed_by_farmer": "Confirmed by farmer",
        "start_call": "Start consented call",
        "call_running": "Call in progress …",
        "real_call": "place a real call",
        "real_call_hint": "A real call uses one of your CALL-E credits.",
        "no_phone_hint": "Set DEMO_PHONE_NUMBER in .env to enable real calls.",
        "review": "Review evidence & approve as a person",
        "approve_export": "Approve selected and export",
        "evidence": "Evidence timeline",
        "package": "Export for portal or case file",
        "no_export": "After human approval, the correction package will be ready to export here.",
        "no_events": "No events yet.",
        "awaiting_call": "awaiting call",
        "confirmed": "confirmed",
        "not_confirmed": "not confirmed",
        "approximate": "approximate value",
        "follow_up_warning": "Not every field was confirmed. Unconfirmed values are never applied – this case needs follow-up.",
        "config_error_warning": "Configuration error during the call. This is not a farmer follow-up.",
        "live_ready": "live calls ready",
        "demo_mode": "demo mode – no phone number configured",
        "confirm_real_call": "This places a REAL call and uses one of your CALL-E credits. Continue?",
        "select_one": "Select at least one confirmed field.",
        "status_needs_information": "Needs information",
        "status_call_in_progress": "Call in progress",
        "status_awaiting_review": "Awaiting review",
        "status_needs_follow_up": "Needs follow-up",
        "status_closed": "Closed",
        "shortcuts_title": "Keyboard shortcuts",
        "shortcuts_hint": "Press ? for keyboard shortcuts",
        "shortcuts_close_hint": "Press Esc to close",
        "shortcut_move": "Move between fields",
        "shortcut_toggle": "Toggle approval (confirmed fields only)",
        "shortcut_approve": "Approve selected and export",
        "shortcut_call": "Start a call",
        "shortcut_help": "Show or hide this help",
        "shortcut_escape": "Close this help",
        "original_value": "Original value",
        "proposed_value": "Proposed value",
        "question_asked": "Question asked",
        "confirmation_state": "Confirmation status",
        "timestamp": "Timestamp",
        "timeline_col_time": "Time",
        "timeline_col_event": "Event",
        "timeline_col_field": "Field",
        "print_generated": "Printed on",
        "scheme_heading": "Funding scheme",
        "at_stake": "What's at stake",
        "why_heading": "Why this matters",
        "note_label": "Technical note",
        "spoken_label": "As spoken",
        "source_label": "Source",
        "raw_data": "Raw data (for developers)",
        "select_column": "Select",
        "tl_case_imported": "Case created",
        "tl_missing_fields_identified": "Missing fields identified",
        "tl_answer_captured": "Answer recorded: {field}",
        "tl_status_changed": "Status: {old} → {new}",
        "tl_reviewed": "Approved by {reviewer}",
        "tl_call_started": "Call started",
        "tl_call_ended": "Call ended: {outcome}",
        "tl_call_failed": "Call failed",
        "tl_call_configuration_error": "Configuration error during call",
        "tl_transcript_recorded": "Transcript recorded",
        "tl_call_language_changed": "Call language changed: {language}",
        "tl_unknown_event": "Other event",
        "outcome_completed": "completed",
        "outcome_partial": "partially answered",
        "outcome_unreachable": "unreachable",
        "import_button": "Import CSV",
        "import_label": "Select a CSV file",
        "import_success": "{count} cases imported",
        "import_error": "Error importing",
        "cases_title": "Case list",
        "column_holding": "Holding",
        "column_scheme": "Scheme",
        "column_year": "Year",
        "column_missing": "Missing fields",
        "column_status": "Status",
        "column_activity": "Last activity",
        "back_to_list": "Back to list",
        "no_cases": "No cases yet.",
        "empty_cases_message": "No cases. Upload a CSV file to get started.",
        "loading_text": "Loading …",
        "error_upload_failed": "CSV upload failed: {message}",
        "error_unknown_scheme": "Unknown scheme code in row {row}: {code}",
        "error_call_failed": "Could not connect the call.",
        "error_case_not_found": "Case not found.",
        "activity_just_now": "just now",
        "activity_minutes_ago": "{minutes} min ago",
        "activity_hours_ago": "{hours} h ago",
        "activity_yesterday": "yesterday",
        "activity_days_ago": "{days} days ago",
        "table_field": "Field",
        "table_original": "Original value",
        "table_proposed": "New value",
        "table_confirmed": "Confirmed",
        "table_question": "Question",
        "table_captured": "Captured",
        "status_confirmed": "✓ confirmed",
        "status_unconfirmed": "❌ not confirmed — the farmer did not answer clearly",
        "status_approximate": "⚠️ approximate value — “{value}”",
    },
}

UI["en"].update({
    "demo_scenario": "Simulated call scenario",
    "scenario_confirmed": "Clear answers", "scenario_uncertain": "Approximate / hedged answers",
    "scenario_refused": "Consent declined", "scenario_unreachable": "No answers",
    "scenario_configuration": "Account problem",
    "goal_title": "Verified missing fields", "call_attempt": "Call attempt", "transcript_title": "Read transcript",
    "next_call": "Next: collect the missing information in one consented call.",
    "next_wait": "Call in progress. Wait for the evidence before reviewing.",
    "next_review": "Next: check the evidence and approve the exact, confirmed values.",
    "next_follow_up": "Some answers are unclear or approximate. Obtain exact confirmation before applying them.",
    "next_refused": "Consent was declined. No values were collected. Agree another way to follow up; do not automatically retry.",
    "next_unreachable": "No usable answers were received. Check contact details and arrange a suitable time.",
    "next_failed": "The call service failed. Check the service before retrying. This is not a farmer refusal.",
    "next_configuration": "Account or configuration problem. Fix service access before calling again. The farmer does not need to act.",
    "next_closed": "Case closed. Any approved correction package is available below. Nothing was sent to a government portal.",
    "download_csv": "Download CSV", "download_json": "Download JSON", "print_package": "Print package",
    "status_unconfirmed": "Not confirmed — cannot be applied",
    "status_approximate": "Approximate — exact confirmation needed: “{value}”",
    "journey_title": "From missing information to a safe hand-off",
    "journey_summary": "This case is blocked by {count} missing field(s). AcreVoice gathers evidence; an adviser decides what is exported.",
    "journey_problem": "Problem identified", "journey_call": "Phone call", "journey_evidence": "Evidence captured",
    "journey_approval": "Human approval", "journey_export": "Export hand-off",
})
UI["de"].update({
    "demo_scenario": "Simuliertes Gespräch",
    "scenario_confirmed": "Eindeutige Antworten", "scenario_uncertain": "Ungefähre / unsichere Antworten",
    "scenario_refused": "Einwilligung abgelehnt", "scenario_unreachable": "Keine Antworten",
    "scenario_configuration": "Kontoproblem",
    "goal_title": "Verifizierte fehlende Angaben", "call_attempt": "Anrufversuch", "transcript_title": "Transkript lesen",
    "next_call": "Nächster Schritt: fehlende Angaben in einem Gespräch mit Einwilligung erfragen.",
    "next_wait": "Gespräch läuft. Vor der Prüfung auf die Belege warten.",
    "next_review": "Nächster Schritt: Belege prüfen und exakte, bestätigte Werte freigeben.",
    "next_follow_up": "Einige Angaben sind unsicher oder ungefähr. Vor der Übernahme exakt bestätigen lassen.",
    "next_refused": "Einwilligung abgelehnt. Keine Angaben erhoben. Anderen Kontaktweg vereinbaren; nicht automatisch erneut anrufen.",
    "next_unreachable": "Keine verwertbaren Antworten erhalten. Kontaktdaten und passenden Zeitpunkt prüfen.",
    "next_failed": "Der Anrufdienst ist fehlgeschlagen. Dienst vor erneutem Versuch prüfen. Keine Ablehnung durch den Betrieb.",
    "next_configuration": "Konto- oder Konfigurationsproblem. Dienstzugang vor erneutem Anruf korrigieren. Der Betrieb muss nichts tun.",
    "next_closed": "Fall abgeschlossen. Freigegebene Korrekturen stehen unten bereit. Es wurde nichts an ein Behördenportal gesendet.",
    "download_csv": "CSV herunterladen", "download_json": "JSON herunterladen", "print_package": "Paket drucken",
    "status_unconfirmed": "Nicht bestätigt — keine Übernahme möglich",
    "status_approximate": "Ungefähr — exakte Bestätigung erforderlich: „{value}“",
    "journey_title": "Von fehlenden Angaben zur sicheren Übergabe",
    "journey_summary": "Dieser Fall wird durch {count} fehlende Angabe(n) aufgehalten. AcreVoice sammelt Nachweise; eine Beratung entscheidet über den Export.",
    "journey_problem": "Problem erkannt", "journey_call": "Telefonat", "journey_evidence": "Nachweis erfasst",
    "journey_approval": "Menschliche Freigabe", "journey_export": "Export-Übergabe",
})

# Plain-language field labels, so no raw field name reaches an adviser.
FIELD_LABELS: dict[str, dict[str, str]] = {
    "de": {"area_ha": "Fläche (Hektar)", "cover_crop_used": "Zwischenfrucht angebaut"},
    "en": {"area_ha": "Area (hectares)", "cover_crop_used": "Cover crop planted"},
}


def ui_strings(language: str) -> dict[str, str]:
    if language not in UI:
        raise ValueError(f"Unsupported console language {language!r}; expected one of {SUPPORTED}")
    return UI[language]


def field_label(field: str, language: str) -> str:
    return FIELD_LABELS.get(language, {}).get(field, field.replace("_", " "))
