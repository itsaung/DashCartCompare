"""flight_subcategories: sub-category discovery from the flight payload.

Fixture strings are trimmed from a real Target (2833969) Snacks category page
captured 2026-09-28; that storefront renders no `sub-category/` links.
"""
from doordash_dashmart_scraper import flight_subcategories

SNACKS = (
    '"swatch":null}],"id":"2833969:758","categoryId":"758","urlSlug":"snacks-758",'
    '"name":"Snacks","storeId":"2833969","imageUrl":"https://img.cdn4dd.com/s/managed/convenience/snacks.png",'
    '"totalItemCount":1652,"l2Categories":['
    '{"__typename":"RetailL2Category","id":"2833969:765","subCategoryId":"765","urlSlug":"chips-765","name":"Chips","storeId":"2833969","imageUrl":""},'
    '{"__typename":"RetailL2Category","id":"2833969:1401","subCategoryId":"1401","urlSlug":"nuts & seeds-1401","name":"Nuts & Seeds","storeId":"2833969","imageUrl":""}'
    ']}'
)

BABY = (
    '"swatch":null}],"id":"2833969:1791","categoryId":"1791","urlSlug":"baby & child-1791",'
    '"name":"Baby & Child","storeId":"2833969","imageUrl":"","totalItemCount":300,"l2Categories":['
    '{"__typename":"RetailL2Category","urlSlug":"diapers-1800","name":"Diapers"}]}'
)


def test_owned_list_is_returned_url_quoted():
    assert flight_subcategories(SNACKS, "snacks-758") == {"chips-765", "nuts%20%26%20seeds-1401"}


def test_other_categorys_list_is_ignored():
    assert flight_subcategories(SNACKS, "candy-750") == set()
    assert flight_subcategories(SNACKS + BABY, "snacks-758") == {"chips-765", "nuts%20%26%20seeds-1401"}


def test_quoted_category_slug_matches_unquoted_owner():
    # discover_categories yields slugs as they appear in hrefs (URL-quoted).
    assert flight_subcategories(BABY, "baby%20%26%20child-1791") == {"diapers-1800"}


def test_no_l2_list_or_malformed_list():
    assert flight_subcategories('"urlSlug":"snacks-758","name":"Snacks"', "snacks-758") == set()
    assert flight_subcategories('"urlSlug":"snacks-758","l2Categories":[{bad', "snacks-758") == set()
