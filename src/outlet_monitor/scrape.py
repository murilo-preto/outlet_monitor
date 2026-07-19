import json
import re
import urllib.parse
from datetime import datetime, timezone

import requests

from outlet_monitor.models import ProductSnapshot

# Lenovo's outlet API has no clean "family" field, so category is inferred from
# the product name. Order doesn't matter here since each pattern is anchored to
# a distinct word boundary and Lenovo family names don't overlap as substrings.
CATEGORY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("ThinkPad", re.compile(r"\bThinkPad\b", re.IGNORECASE)),
    ("ThinkBook", re.compile(r"\bThinkBook\b", re.IGNORECASE)),
    ("IdeaPad", re.compile(r"\bIdeaPad\b", re.IGNORECASE)),
    ("Yoga", re.compile(r"\bYoga\b", re.IGNORECASE)),
    ("Legion", re.compile(r"\bLegion\b", re.IGNORECASE)),
    ("LOQ", re.compile(r"\bLOQ\b", re.IGNORECASE)),
    ("V Series", re.compile(r"\bV1[0-9]\b", re.IGNORECASE)),
]

LISTING_PAGE_URL = "https://www.lenovo.com/br/outlet/pt/laptops/"
SITE_ROOT = "https://www.lenovo.com"
API_URL = "https://openapi.lenovo.com/br/outlet/pt/ofp/search/dlp/product/query/get/_tsc"

# Static category/filter ids captured from a live page load (see PLAN.md Phase 0).
# If these go stale, Lenovo will start returning empty result sets rather than an
# error, which fetch_all_products() below treats as a hard failure.
CLASSIFICATION_GROUP_IDS = "400001"
PAGE_FILTER_ID = "8e869e6a-e5b2-4a4b-b190-d4564c4eb084"

PAGE_SIZE = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "pt-BR",
    "Referer": LISTING_PAGE_URL,
}


class ScrapeError(RuntimeError):
    """Raised when the outlet API responds but not in the shape we expect."""


def _build_url(page: int) -> str:
    params_obj = {
        "classificationGroupIds": CLASSIFICATION_GROUP_IDS,
        "pageFilterId": PAGE_FILTER_ID,
        "facets": [],
        "page": str(page),
        "pageSize": PAGE_SIZE,
        "groupCode": "",
        "init": True,
        "sorts": ["priceUp"],
        "version": "v2",
        "enablePreselect": True,
        "subseriesCode": "",
    }
    # The API expects this blob URL-encoded twice (confirmed empirically in Phase 0).
    encoded_params = urllib.parse.quote(
        urllib.parse.quote(json.dumps(params_obj, separators=(",", ":")))
    )
    query = urllib.parse.urlencode(
        {"pageFilterId": PAGE_FILTER_ID, "subSeriesCode": "", "loyalty": "false"}
    )
    return f"{API_URL}?{query}&params={encoded_params}"


def _fetch_raw_page(session: requests.Session, page: int) -> dict:
    resp = session.get(_build_url(page), headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _infer_category(name: str) -> str:
    for label, pattern in CATEGORY_PATTERNS:
        if pattern.search(name):
            return label
    return "Other"


def _extract_image_url(raw: dict) -> str:
    media = raw.get("media") or {}
    address = ((media.get("heroImage") or {}).get("imageAddress")) or ""
    if not address:
        gallery = media.get("gallery") or []
        address = gallery[0].get("imageAddress", "") if gallery else ""
    return "https:" + address if address.startswith("//") else address


def _extract_specs(raw: dict) -> list[dict[str, str]]:
    return [
        {"label": entry["a"], "value": entry["b"]}
        for entry in raw.get("classification", [])
        if entry.get("b")
    ]


def _parse_product(raw: dict, timestamp: datetime) -> ProductSnapshot:
    structured_specs = _extract_specs(raw)
    # Flattened summary kept for backwards compatibility; note it's lossy for
    # display purposes (some values, e.g. "Tela", contain commas of their own,
    # indistinguishable from the join separator) — use `specs` for anything
    # that needs the individual label/value pairs back out.
    specs = ", ".join(f"{entry['label']}: {entry['value']}" for entry in structured_specs)
    return ProductSnapshot(
        timestamp=timestamp,
        product_id=raw["id"],
        sku=raw["productCode"],
        name=raw["productName"],
        url=SITE_ROOT + raw["url"],
        list_price=float(raw["webPrice"]),
        sale_price=float(raw["finalPrice"]),
        discount_pct=float(raw["savePercent"]),
        condition=raw.get("productCondition", ""),
        availability=raw.get("marketingStatus", ""),
        raw_specs=specs,
        category=_infer_category(raw["productName"]),
        image_url=_extract_image_url(raw),
        specs=structured_specs,
    )


def fetch_all_products(session: requests.Session | None = None) -> list[ProductSnapshot]:
    """Fetch every laptop listing in the Lenovo BR outlet, across all pages.

    Raises ScrapeError if the API responds successfully but returns zero
    products — this almost always means PAGE_FILTER_ID/CLASSIFICATION_GROUP_IDS
    have gone stale, not that the outlet is genuinely empty.
    """
    owns_session = session is None
    session = session or requests.Session()
    timestamp = datetime.now(timezone.utc)

    try:
        products: list[ProductSnapshot] = []
        page = 1
        page_count = 1
        while page <= page_count:
            data = _fetch_raw_page(session, page)
            if data.get("status") != 200:
                raise ScrapeError(f"API returned non-200 status payload: {data.get('msg')!r}")

            page_count = data["data"]["pageCount"]
            for group in data["data"]["data"]:
                for raw_product in group.get("products", []):
                    products.append(_parse_product(raw_product, timestamp))

            page += 1

        if not products:
            raise ScrapeError(
                "API returned zero products across all pages — likely a stale "
                "PAGE_FILTER_ID/CLASSIFICATION_GROUP_IDS, not an empty outlet."
            )

        return products
    finally:
        if owns_session:
            session.close()
