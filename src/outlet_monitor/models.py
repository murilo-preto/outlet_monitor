from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ProductSnapshot:
    timestamp: datetime
    product_id: str
    sku: str
    name: str
    url: str
    list_price: float
    sale_price: float
    discount_pct: float
    condition: str
    availability: str
    raw_specs: str
    category: str
    image_url: str
    specs: list[dict[str, str]] = field(default_factory=list)
