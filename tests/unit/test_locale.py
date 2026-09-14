import pytest

from acrevoice.locale import SUPPORTED, consent_for, get_script, question_for, read_back_for


@pytest.mark.parametrize("language", SUPPORTED)
def test_every_language_has_a_complete_script(language):
    script = get_script(language)
    assert script.consent and script.read_back and script.refused and script.closing
    assert set(script.question) == {"area_ha", "cover_crop_used"}


@pytest.mark.parametrize("language", SUPPORTED)
def test_templates_render_without_leftover_placeholders(language):
    rendered = " ".join([
        consent_for(language, year="2026", count=2),
        question_for("area_ha", language, parcel_id="BY-4821-07"),
        read_back_for(language, value="42.5"),
    ])
    assert "{" not in rendered and "}" not in rendered


def test_german_uses_domain_vocabulary():
    text = question_for("cover_crop_used", "de", parcel_id="BY-1")
    assert "Zwischenfrucht" in text  # not a literal translation of "cover crop"


def test_unknown_field_still_produces_a_question():
    assert question_for("some_new_field", "de")
    assert question_for("some_new_field", "en")


def test_unsupported_language_is_rejected():
    with pytest.raises(ValueError):
        get_script("fr")


def test_console_and_field_labels_have_full_language_parity():
    """A missing key in one language would show a raw identifier to an adviser."""
    from acrevoice.locale import FIELD_LABELS, UI

    assert set(UI["de"]) == set(UI["en"]), set(UI["de"]) ^ set(UI["en"])
    assert set(FIELD_LABELS["de"]) == set(FIELD_LABELS["en"])
    for lang in ("de", "en"):
        assert all(v.strip() for v in UI[lang].values()), f"empty UI string in {lang}"


# Strings that are correctly identical in both languages:
#   app_name          - a product name, not translated
#   status            - "Status" is the ordinary German word, not an oversight
#   tl_status_changed - "Status: {old} -> {new}" reads the same in both; the
#                        translated work happens in the old/new status labels
#   column_status     - same reasoning as "status": the case-list column header
LEGITIMATELY_IDENTICAL = {"app_name", "status", "tl_status_changed", "column_status"}


def test_the_two_languages_are_actually_different():
    """Guards against an untranslated copy-paste leaving English in a German console."""
    from acrevoice.locale import UI

    shared = {k for k in UI["de"] if UI["de"][k] == UI["en"][k]}
    untranslated = shared - LEGITIMATELY_IDENTICAL
    assert not untranslated, f"untranslated console strings: {untranslated}"


def test_field_labels_are_never_raw_identifiers():
    from acrevoice.locale import field_label

    for lang in ("de", "en"):
        for field in ("area_ha", "cover_crop_used"):
            assert "_" not in field_label(field, lang)
