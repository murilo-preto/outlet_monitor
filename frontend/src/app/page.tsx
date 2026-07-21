"use client";

import { motion } from "framer-motion";
import { BellRing } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { CategoryTabs } from "@/components/CategoryTabs";
import { ProductCarousel } from "@/components/ProductCarousel";
import { ProductDetail } from "@/components/ProductDetail";
import { ProductsTable } from "@/components/ProductsTable";
import { ScrapeButton } from "@/components/ScrapeButton";
import { SiteHeader } from "@/components/SiteHeader";
import { getCategories, getProducts } from "@/lib/api";
import type { CategoryCount, Product } from "@/lib/types";

export default function Home() {
  const [categories, setCategories] = useState<CategoryCount[]>([]);
  const [allProducts, setAllProducts] = useState<Product[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [fetchedCategoryProducts, setFetchedCategoryProducts] = useState<Product[]>([]);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // null selectedCategory means "Todos" (all categories) — mirror allProducts
  // directly rather than re-fetching the same data from the API.
  const categoryProducts = selectedCategory === null ? allProducts : fetchedCategoryProducts;
  const selectedProduct =
    categoryProducts.find((p) => p.product_id === selectedProductId) ?? categoryProducts[0] ?? null;

  const loadOverview = useCallback(async () => {
    setError(null);
    try {
      const [cats, products] = await Promise.all([getCategories(), getProducts()]);
      setCategories(cats);
      setAllProducts(products);
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

  useEffect(() => {
    if (selectedCategory === null) return;
    let cancelled = false;
    getProducts(selectedCategory).then((products) => {
      if (!cancelled) setFetchedCategoryProducts(products);
    });
    return () => {
      cancelled = true;
    };
  }, [selectedCategory]);

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
              <ProductCarousel
                products={categoryProducts}
                selectedId={selectedProduct?.product_id ?? null}
                onSelect={(product) => setSelectedProductId(product.product_id)}
              />
            </section>

            <ProductDetail product={selectedProduct} />

            <section className="flex flex-col gap-4">
              <h2 className="text-lg font-semibold text-ink">Produtos disponíveis no outlet</h2>
              <ProductsTable products={categoryProducts} />
            </section>
          </>
        )}
      </main>
    </div>
  );
}
