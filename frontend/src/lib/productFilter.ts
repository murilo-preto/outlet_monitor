import type { Product } from "./types";

export interface ProductFilters {
  search: string;
  minRamGb: number | null;
  minStorageGb: number | null;
  maxPrice: number | null;
  discreteGpuOnly: boolean;
}

export const DEFAULT_FILTERS: ProductFilters = {
  search: "",
  minRamGb: null,
  minStorageGb: null,
  maxPrice: null,
  discreteGpuOnly: false,
};

export function hasActiveFilters(filters: ProductFilters): boolean {
  return (
    filters.search.trim() !== "" ||
    filters.minRamGb !== null ||
    filters.minStorageGb !== null ||
    filters.maxPrice !== null ||
    filters.discreteGpuOnly
  );
}

/** Strip accents so "memoria" matches "Memória" and vice versa. */
function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

/**
 * Filtering happens here rather than on the server because the page already
 * holds every product for the selected category in memory. Sending each
 * keystroke to Flask would add a round-trip and a full table scan to filter a
 * list that is already local.
 *
 * Null handling is a deliberate rule, not a side effect of null comparisons:
 * a product whose spec could not be parsed is *excluded* by a minimum on that
 * spec. Asking for "16 GB or more" should not return machines whose memory is
 * unknown.
 */
export function applyFilters(products: Product[], filters: ProductFilters): Product[] {
  const needle = fold(filters.search.trim());

  return products.filter((product) => {
    if (needle) {
      const haystack = fold(`${product.name} ${product.cpu_model ?? ""} ${product.raw_specs}`);
      if (!haystack.includes(needle)) return false;
    }
    if (filters.minRamGb !== null && (product.ram_gb ?? -1) < filters.minRamGb) return false;
    if (filters.minStorageGb !== null && (product.storage_gb ?? -1) < filters.minStorageGb) {
      return false;
    }
    if (filters.maxPrice !== null && product.sale_price > filters.maxPrice) return false;
    if (filters.discreteGpuOnly && product.gpu_discrete !== true) return false;
    return true;
  });
}

export interface FilterOptions {
  ramValues: number[];
  storageValues: number[];
  priceMax: number;
}

/**
 * Choices derived from the loaded data, so the UI can never offer a value that
 * matches nothing.
 */
export function filterOptions(products: Product[]): FilterOptions {
  const ram = new Set<number>();
  const storage = new Set<number>();
  let priceMax = 0;

  for (const product of products) {
    if (product.ram_gb !== null) ram.add(product.ram_gb);
    if (product.storage_gb !== null) storage.add(product.storage_gb);
    if (product.sale_price > priceMax) priceMax = product.sale_price;
  }

  return {
    ramValues: [...ram].sort((a, b) => a - b),
    storageValues: [...storage].sort((a, b) => a - b),
    priceMax: Math.ceil(priceMax),
  };
}
