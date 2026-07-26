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
  // Derived from `specs` server-side. null means the parser could not read the
  // value — treat as unknown, never as zero.
  ram_gb: number | null;
  storage_gb: number | null;
  screen_in: number | null;
  cpu_brand: string | null;
  cpu_model: string | null;
  gpu_discrete: boolean | null;
  lowest_price: number;
  highest_price: number;
  currently_listed: boolean;
  snapshot_count: number;
  first_seen: string;
  days_tracked: number;
  // null means "not enough price history to tell" — render that as nothing,
  // never as "not a record low".
  at_all_time_low: boolean | null;
  pct_below_high: number;
  deal_score: number;
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
