import json

from app.services.styleguide_importer import DEFAULT_STYLEGUIDE_PATH, categories_from_styleguide


def test_categories_from_beerjson_groups_styles_by_category() -> None:
    data = json.loads(DEFAULT_STYLEGUIDE_PATH.read_text())

    categories = categories_from_styleguide(data)
    ipa = next(category for category in categories if category["code"] == "21")
    historical = next(category for category in categories if category["code"] == "27")
    wood = next(category for category in categories if category["code"] == "33")
    subcategory_codes = {subcategory["code"] for subcategory in ipa["subcategories"]}

    assert len(categories) == 34
    assert ipa["name"] == "IPA"
    assert historical["name"] == "Historical Beer"
    assert wood["name"] == "Wood Beer"
    assert {"21A", "21B", "21C"}.issubset(subcategory_codes)
