from datetime import datetime, timezone

import pytest
import requests

import outlet_monitor.scrape as scrape_module
from outlet_monitor.scrape import (
    ScrapeError,
    _build_url,
    _infer_category,
    _parse_product,
    fetch_all_products,
)

RAW_PRODUCT = {
    "id": "82X5X00900_64c9a7c6b7468-4a6c-b2f7-695ca23a0803",
    "productCode": "82X5X00900",
    "productName": 'IdeaPad 1i Intel Core i3-1215U 4GB 256GB SSD Linux 14" HD',
    "webPrice": "2634.99",
    "finalPrice": "2252.92",
    "savePercent": "14",
    "marketingStatus": "Available",
    "productCondition": "Remanufaturado Certificado",
    "url": "/p/laptops/ideapad/ideapad-100/88ips101778/82x5x00900",
    "classification": [
        {"a": "Processador", "b": "AMD Ryzen 3 7320U"},
        {"a": "Memória", "b": "4GB"},
        {"a": "Garantia", "b": ""},
    ],
    "media": {
        "heroImage": {"imageAddress": "//p3-ofp.static.pub/fes/cms/2021/10/25/hero.png"},
        "gallery": [{"imageAddress": "//p3-ofp.static.pub/fes/cms/2021/10/25/gallery0.png"}],
    },
}


def test_parse_product_maps_fields():
    timestamp = datetime(2026, 7, 19, tzinfo=timezone.utc)
    snapshot = _parse_product(RAW_PRODUCT, timestamp)

    assert snapshot.timestamp == timestamp
    assert snapshot.product_id == "82X5X00900_64c9a7c6b7468-4a6c-b2f7-695ca23a0803"
    assert snapshot.sku == "82X5X00900"
    assert snapshot.url == "https://www.lenovo.com/br/outlet/pt/p/laptops/ideapad/ideapad-100/88ips101778/82x5x00900"
    assert snapshot.list_price == 2634.99
    assert snapshot.sale_price == 2252.92
    assert snapshot.discount_pct == 14.0
    assert snapshot.condition == "Remanufaturado Certificado"
    assert snapshot.availability == "Available"
    assert snapshot.category == "IdeaPad"
    assert snapshot.image_url == "https://p3-ofp.static.pub/fes/cms/2021/10/25/hero.png"


def test_parse_product_skips_blank_spec_values():
    snapshot = _parse_product(RAW_PRODUCT, datetime.now(timezone.utc))

    assert snapshot.raw_specs == "Processador: AMD Ryzen 3 7320U, Memória: 4GB"
    assert snapshot.specs == [
        {"label": "Processador", "value": "AMD Ryzen 3 7320U"},
        {"label": "Memória", "value": "4GB"},
    ]


def test_parse_product_falls_back_to_gallery_image_when_no_hero():
    raw = {**RAW_PRODUCT, "media": {"gallery": RAW_PRODUCT["media"]["gallery"]}}
    snapshot = _parse_product(raw, datetime.now(timezone.utc))

    assert snapshot.image_url == "https://p3-ofp.static.pub/fes/cms/2021/10/25/gallery0.png"


def test_infer_category_matches_known_families():
    assert _infer_category('ThinkPad T14 Intel Core i5-1145G7 vPro 16GB 512GB SSD') == "ThinkPad"
    assert _infer_category('ThinkBook 14 G6') == "ThinkBook"
    assert _infer_category('IdeaPad 1i Intel Core i3-1215U') == "IdeaPad"
    assert _infer_category('Yoga 7i 14IAH10') == "Yoga"
    assert _infer_category('Legion 5 Intel Core i7') == "Legion"
    assert _infer_category('LOQ 15IRX9') == "LOQ"
    assert _infer_category('Lenovo V14 AMD Ryzen 5 7520U') == "V Series"
    assert _infer_category('Some Unknown Laptop Name') == "Other"


def _raw(product_id: str) -> dict:
    return {**RAW_PRODUCT, "id": product_id, "productCode": product_id.split("_")[0]}


def _fake_pages(pages: list[list[dict]], monkeypatch) -> None:
    """Serve `pages` (a list of per-page product lists) to fetch_all_products."""

    def fake_fetch(_session, page: int) -> dict:
        return {
            "status": 200,
            "data": {"pageCount": len(pages), "data": [{"products": pages[page - 1]}]},
        }

    monkeypatch.setattr(scrape_module, "_fetch_raw_page", fake_fetch)


def test_fetch_all_products_drops_ids_repeated_across_pages(monkeypatch):
    # A product on a page boundary comes back on both pages when the live,
    # price-sorted result set shifts between the two requests.
    _fake_pages([[_raw("a"), _raw("b")], [_raw("b"), _raw("c")]], monkeypatch)

    products = fetch_all_products()

    assert [p.product_id for p in products] == ["a", "b", "c"]


def test_fetch_all_products_keeps_the_first_copy_of_a_duplicate(monkeypatch):
    first = {**_raw("a"), "finalPrice": "1000.00"}
    second = {**_raw("a"), "finalPrice": "2000.00"}
    _fake_pages([[first], [second]], monkeypatch)

    products = fetch_all_products()

    assert [p.sale_price for p in products] == [1000.00]


def test_fetch_all_products_shares_one_timestamp_across_pages(monkeypatch):
    _fake_pages([[_raw("a")], [_raw("b")]], monkeypatch)

    products = fetch_all_products()

    assert len({p.timestamp for p in products}) == 1


def test_fetch_raw_page_sends_the_headers_the_edge_waf_requires():
    # Lenovo's edge sits behind an openresty WAF that checks User-Agent and
    # Referer (PLAN.md Phase 0). Dropping either turns every scrape into a
    # rejection, so the headers and the timeout are pinned here.
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"status": 200}

    class FakeSession:
        def get(self, url, headers=None, timeout=None):
            captured.update(url=url, headers=headers, timeout=timeout)
            return FakeResponse()

    scrape_module._fetch_raw_page(FakeSession(), 1)

    assert captured["timeout"] == 15
    assert "Mozilla/5.0" in captured["headers"]["User-Agent"]
    assert captured["headers"]["Referer"] == scrape_module.LISTING_PAGE_URL
    assert captured["headers"]["Accept-Language"] == "pt-BR"


def test_fetch_all_products_treats_an_empty_result_set_as_a_failure(monkeypatch):
    # PLAN.md's top risk: when PAGE_FILTER_ID/CLASSIFICATION_GROUP_IDS go
    # stale, Lenovo answers 200 with zero products rather than an error. If
    # that were ever treated as "the outlet is empty today", every tracked
    # product would silently look delisted and the history would rot.
    _fake_pages([[]], monkeypatch)

    with pytest.raises(ScrapeError, match="zero products"):
        fetch_all_products()


def test_fetch_all_products_rejects_a_non_200_status_payload(monkeypatch):
    # The HTTP response is 200; the failure is inside the JSON body, so
    # raise_for_status() never sees it.
    def fake_fetch(_session, page: int) -> dict:
        return {"status": 500, "msg": "internal error"}

    monkeypatch.setattr(scrape_module, "_fetch_raw_page", fake_fetch)

    with pytest.raises(ScrapeError, match="non-200 status payload"):
        fetch_all_products()


def test_fetch_all_products_does_not_swallow_transport_errors(monkeypatch):
    # A timeout mid-pagination must abort the run rather than persisting a
    # partial catalogue, which would read as a mass delisting.
    def fake_fetch(_session, page: int) -> dict:
        raise requests.Timeout("read timed out")

    monkeypatch.setattr(scrape_module, "_fetch_raw_page", fake_fetch)

    with pytest.raises(requests.Timeout):
        fetch_all_products()


def test_build_url_double_encodes_page_number():
    url = _build_url(2)

    assert "params=" in url
    # the literal digit "2" must not appear unencoded next to "page" in the query
    assert "%2522page%2522%253A%25222%2522" in url
