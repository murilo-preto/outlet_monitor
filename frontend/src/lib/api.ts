import type { CategoryCount, Product, ScrapeResult } from "./types";

// Relative paths — these hit this app's own Route Handlers (frontend/src/app/api/*),
// which proxy server-side to the Flask API over the internal Docker network.
// The browser never talks to Flask directly, in dev or prod.

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    throw new Error(`${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function getCategories(): Promise<CategoryCount[]> {
  return getJSON<CategoryCount[]>("/api/categories");
}

export function getProducts(category?: string): Promise<Product[]> {
  const query = category ? `?category=${encodeURIComponent(category)}` : "";
  return getJSON<Product[]>(`/api/products${query}`);
}

export function getProductHistory(productId: string): Promise<Product[]> {
  return getJSON<Product[]>(`/api/products/${encodeURIComponent(productId)}/history`);
}

export class ScrapeAuthError extends Error {
  constructor() {
    super("invalid or missing scrape token");
    this.name = "ScrapeAuthError";
  }
}

export async function triggerScrape(token?: string): Promise<ScrapeResult> {
  const res = await fetch("/api/scrape", {
    method: "POST",
    headers: token ? { "x-scrape-token": token } : undefined,
  });
  if (res.status === 401) {
    throw new ScrapeAuthError();
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error ?? `scrape failed: ${res.status}`);
  }
  return res.json() as Promise<ScrapeResult>;
}
