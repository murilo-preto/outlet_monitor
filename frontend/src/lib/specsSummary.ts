import type { Product } from "./types";

/**
 * The parsed specs as short chips, skipping anything unknown.
 *
 * A summary, not a replacement for the raw label/value table — those carry
 * detail (panel type, memory channel layout, cache) this deliberately drops.
 */
export function specsSummary(product: Product): string[] {
  const chips: string[] = [];

  if (product.ram_gb !== null) chips.push(`${product.ram_gb} GB RAM`);
  if (product.storage_gb !== null) {
    chips.push(
      product.storage_gb >= 1024 ? `${product.storage_gb / 1024} TB` : `${product.storage_gb} GB`
    );
  }
  if (product.screen_in !== null) {
    chips.push(`${String(product.screen_in).replace(".", ",")}"`);
  }
  if (product.cpu_model !== null) {
    chips.push(product.cpu_brand ? `${product.cpu_brand} ${product.cpu_model}` : product.cpu_model);
  }
  if (product.gpu_discrete === true) chips.push("Placa dedicada");

  return chips;
}
