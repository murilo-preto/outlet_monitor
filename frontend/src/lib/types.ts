export interface Product {
  id: number;
  timestamp: string;
  product_id: string;
  sku: string;
  name: string;
  url: string;
  list_price: number;
  sale_price: number;
  discount_pct: number;
  condition: string;
  availability: string;
  raw_specs: string;
  category: string;
  image_url: string;
  specs: { label: string; value: string }[];
}

export interface CategoryCount {
  category: string;
  product_count: number;
}

export interface ScrapeResult {
  fetched: number;
  written: number;
  timestamp: string;
}
