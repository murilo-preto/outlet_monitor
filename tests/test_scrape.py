from datetime import datetime, timezone

from outlet_monitor.scrape import _build_url, _infer_category, _parse_product

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


def test_build_url_double_encodes_page_number():
    url = _build_url(2)

    assert "params=" in url
    # the literal digit "2" must not appear unencoded next to "page" in the query
    assert "%2522page%2522%253A%25222%2522" in url
