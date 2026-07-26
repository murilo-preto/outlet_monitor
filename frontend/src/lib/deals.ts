import type { Product } from "./types";

// Below this the badge would be noise — a 2% dip off a product's own peak is
// not worth drawing the eye to.
const MIN_PCT_BELOW_HIGH_TO_SHOW = 5;

/** Products worth surfacing as deals, best first. */
export function topDeals(products: Product[], limit = 6): Product[] {
  return products
    .filter((p) => p.currently_listed && p.deal_score > 0)
    .sort((a, b) => b.deal_score - a.deal_score)
    .slice(0, limit);
}

/** Whether a product has moved enough off its own peak to be worth a badge. */
export function hasNotableDrop(product: Product): boolean {
  return product.pct_below_high >= MIN_PCT_BELOW_HIGH_TO_SHOW && product.deal_score > 0;
}
