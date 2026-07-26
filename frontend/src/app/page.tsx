"use client";

import { motion } from "framer-motion";
import { BellRing } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { BestDeals } from "@/components/BestDeals";
import { CategoryTabs } from "@/components/CategoryTabs";
import { ExportButton } from "@/components/ExportButton";
import { LastUpdated } from "@/components/LastUpdated";
import { ProductCarousel } from "@/components/ProductCarousel";
import { ProductDetail } from "@/components/ProductDetail";
import { ProductFilters } from "@/components/ProductFilters";
import { ProductsTable } from "@/components/ProductsTable";
import { ScrapeButton } from "@/components/ScrapeButton";
import { SiteHeader } from "@/components/SiteHeader";
import { getCategories, getProducts, getStatus } from "@/lib/api";
import {
  DEFAULT_FILTERS,
  applyFilters,
  filterOptions,
  type ProductFilters as ProductFilterState,
} from "@/lib/productFilter";
import type { CategoryCount, Product, ScrapeStatus } from "@/lib/types";

export default function Home() {
  const [categories, setCategories] = useState<CategoryCount[]>([]);
  const [allProducts, setAllProducts] = useState<Product[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [filters, setFilters] = useState<ProductFilterState>(DEFAULT_FILTERS);
  const [status, setStatus] = useState<ScrapeStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Derived, not fetched. /products?category=X returns exactly this filter —
  // the API appends its WHERE after the same joins, so the round-trip bought
  // nothing but latency. It also rendered the *previous* category's products
  // for the duration of each fetch, which in turn selected a product from the
  // wrong category and fired a third request for its price history.
  const categoryProducts = useMemo(
    () =>
      selectedCategory === null
        ? allProducts
        : allProducts.filter((p) => p.category === selectedCategory),
    [allProducts, selectedCategory]
  );

  const visibleProducts = useMemo(
    () => applyFilters(categoryProducts, filters),
    [categoryProducts, filters]
  );
  // Options come from the whole category, not the filtered set, so narrowing
  // one filter never removes the choices you would use to widen it again.
  const options = useMemo(() => filterOptions(categoryProducts), [categoryProducts]);

  // Falls back within the *visible* set: otherwise the detail panel keeps
  // showing a product the user just filtered away.
  const selectedProduct =
    visibleProducts.find((p) => p.product_id === selectedProductId) ?? visibleProducts[0] ?? null;

  const loadOverview = useCallback(async () => {
    setError(null);
    try {
      // Status rides along here so the ScrapeButton's onDone refreshes it too,
      // but it must never be able to fail the page: it is a decorative
      // freshness line, and an API too old to serve /status (or a rolling
      // deploy mid-flight) would otherwise blank out products that loaded fine.
      const [cats, products, scrapeStatus] = await Promise.all([
        getCategories(),
        getProducts(),
        getStatus().catch(() => null),
      ]);
      setCategories(cats);
      setAllProducts(products);
      setStatus(scrapeStatus);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao carregar dados");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Initial data load — fetch-on-mount, the standard pattern for a page
    // with no server-rendered data to hydrate from (see PLAN.md's note on
    // NEXT_PUBLIC_API_URL only being reachable client-side).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadOverview();
  }, [loadOverview]);

  return (
    <div className="flex min-h-screen flex-col bg-page">
      <SiteHeader>
        <Link
          href="/alertas"
          className="flex items-center gap-2 rounded-full bg-accent px-4 py-2 text-sm font-medium text-accent-ink transition-transform hover:scale-[1.03]"
        >
          <BellRing className="h-4 w-4" />
          <span className="hidden sm:inline">Alertas no Telegram</span>
          <span className="sm:hidden">Alertas</span>
        </Link>
        <ExportButton />
        <ScrapeButton onDone={loadOverview} />
      </SiteHeader>

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-12 px-6 py-12">
        <motion.section
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="flex flex-col gap-6"
        >
          <div className="flex flex-col gap-3">
            <h1 className="text-4xl font-semibold tracking-tight text-ink md:text-5xl">
              Acompanhe os preços do <span className="text-accent">outlet Lenovo</span>
            </h1>
            <p className="max-w-xl text-base text-ink-secondary">
              Veja a variação de preço dos notebooks ThinkPad, IdeaPad, Yoga e outras linhas
              ao longo do tempo, organizados por categoria.
            </p>
            <LastUpdated status={status} />
          </div>
        </motion.section>

        {error && (
          <div className="rounded-xl border border-critical px-4 py-3 text-sm text-critical">{error}</div>
        )}

        {loading ? (
          <div className="animate-pulse text-sm text-ink-muted">Carregando...</div>
        ) : categories.length === 0 ? (
          <div className="rounded-2xl border border-border p-10 text-center text-sm text-ink-muted">
            Nenhum produto ainda. Clique em &ldquo;Atualizar preços&rdquo; para buscar dados do outlet.
          </div>
        ) : (
          <>
            <section className="flex flex-col gap-4">
              <CategoryTabs categories={categories} selected={selectedCategory} onSelect={setSelectedCategory} />
              <ProductFilters
                filters={filters}
                options={options}
                onChange={setFilters}
                matchCount={visibleProducts.length}
                totalCount={categoryProducts.length}
              />
              <ProductCarousel
                products={visibleProducts}
                selectedId={selectedProduct?.product_id ?? null}
                onSelect={(product) => setSelectedProductId(product.product_id)}
              />
            </section>

            <BestDeals
              products={visibleProducts}
              selectedId={selectedProduct?.product_id ?? null}
              onSelect={(product) => setSelectedProductId(product.product_id)}
            />

            <ProductDetail product={selectedProduct} />

            <section className="flex flex-col gap-4">
              <h2 className="text-lg font-semibold text-ink">Produtos disponíveis no outlet</h2>
              <ProductsTable products={visibleProducts} />
            </section>
          </>
        )}
      </main>
    </div>
  );
}
