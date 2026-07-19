"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ExternalLink, Package, Tag } from "lucide-react";
import { useEffect, useState } from "react";

import { PriceHistoryChart } from "./PriceHistoryChart";
import { SpecsTable } from "./SpecsTable";
import { getProductHistory } from "@/lib/api";
import { getCategoryStyle } from "@/lib/categoryStyles";
import { formatBRL } from "@/lib/format";
import type { Product } from "@/lib/types";

interface ProductDetailProps {
  product: Product | null;
}

export function ProductDetail({ product }: ProductDetailProps) {
  return (
    <AnimatePresence mode="wait">
      {product && <ProductDetailContent key={product.product_id} product={product} />}
    </AnimatePresence>
  );
}

function ProductDetailContent({ product }: { product: Product }) {
  // Keyed by product.product_id in the parent, so a new instance (and a fresh
  // empty `history`) mounts whenever the selected product changes.
  const [history, setHistory] = useState<Product[]>([]);

  useEffect(() => {
    let cancelled = false;
    getProductHistory(product.product_id).then((rows) => {
      if (!cancelled) setHistory(rows);
    });
    return () => {
      cancelled = true;
    };
  }, [product.product_id]);

  const style = getCategoryStyle(product.category);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.25 }}
      className="grid gap-6 rounded-3xl border border-border bg-surface p-6 md:grid-cols-[280px_1fr] md:p-8"
    >
      <div className="flex flex-col gap-4">
        <div className="flex h-48 items-center justify-center rounded-2xl bg-surface-raised p-4">
          {product.image_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={product.image_url} alt={product.name} className="h-full w-full object-contain" />
          ) : (
            <Package className="h-12 w-12 text-ink-muted" />
          )}
        </div>

        <div className="flex items-center gap-1.5 text-xs text-ink-muted">
          <Tag className={`h-3.5 w-3.5 ${style.textClassName}`} />
          {product.category} · {product.condition}
        </div>

        <h2 className="text-lg font-semibold text-ink">{product.name}</h2>

        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-semibold text-ink">{formatBRL(product.sale_price)}</span>
          {product.list_price > product.sale_price && (
            <span className="text-sm text-ink-muted line-through">{formatBRL(product.list_price)}</span>
          )}
        </div>
        {product.discount_pct > 0 && (
          <span className="text-sm font-medium text-good">
            {Math.round(product.discount_pct)}% de desconto
          </span>
        )}

        <a
          href={product.url}
          target="_blank"
          rel="noreferrer"
          className="mt-auto flex items-center gap-1.5 text-sm font-medium text-accent"
        >
          Ver na Lenovo
          <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </div>

      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-3">
          <h3 className="text-sm font-medium text-ink-secondary">Histórico de preço</h3>
          <PriceHistoryChart history={history} />
        </div>

        {product.specs.length > 0 && (
          <div className="flex flex-col gap-3">
            <h3 className="text-sm font-medium text-ink-secondary">Especificações</h3>
            <SpecsTable specs={product.specs} />
          </div>
        )}
      </div>
    </motion.div>
  );
}
