"""English is the demo default without removing German farmer support."""

from acrevoice.sources import match_sources


def test_english_source_card_explains_official_german_publisher():
    card = match_sources(land="Bayern", topic="eco_scheme", language="en")[0]
    assert "Bavarian State Ministry" in card["publisher_display"]
    assert card["title"] == "Eco-schemes: 2025 guidance note"
