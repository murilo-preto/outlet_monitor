"use client";

import { motion } from "framer-motion";
import { Package } from "lucide-react";

import { getCategoryStyle } from "@/lib/categoryStyles";
import { formatBRL } from "@/lib/format";
import type { Product } from "@/lib/types";

interface ProductCardProps {
  product: Product;
  selected: boolean;
  onSelect: (product: Product) => void;
}

export function ProductCard({ product, selected, onSelect }: ProductCardProps) {
  const style = getCategoryStyle(product.category);
  const available = product.availability.toLowerCase() === "available";

  return (
    <motion.button
      onClick={() => onSelect(product)}
      whileHover={{ y: -4 }}
      whileTap={{ scale: 0.98 }}
      className={`flex w-64 shrink-0 flex-col overflow-hidden rounded-2xl border bg-surface text-left transition-shadow ${
        selected ? "border-accent ring-2 ring-accent" : "border-border"
      }`}
    >
      <div className="relative flex h-40 items-center justify-center bg-surface-raised p-4">
        {product.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={product.image_url}
            alt={product.name}
            loading="lazy"
            className="h-full w-full object-contain"
          />
        ) : (
          <Package className="h-10 w-10 text-ink-muted" />
        )}

        {product.discount_pct > 0 && (
          <span className="absolute top-2 right-2 rounded-full bg-good px-2 py-0.5 text-xs font-semibold text-white">
            -{Math.round(product.discount_pct)}%
          </span>
        )}
      </div>

      <div className="flex flex-1 flex-col gap-2 p-4">
        <div className="flex items-center gap-1.5 text-xs text-ink-muted">
          <span className={`h-1.5 w-1.5 rounded-full ${style.dotClassName}`} />
          {product.category}
          <span
            className={`ml-auto flex items-center gap-1 ${available ? "text-good" : "text-critical"}`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${available ? "bg-good" : "bg-critical"}`} />
            {available ? "Disponível" : "Indisponível"}
          </span>
        </div>

        <h3 className="line-clamp-2 text-sm font-medium text-ink">{product.name}</h3>

        <div className="mt-auto flex items-baseline gap-2">
          <span className="text-lg font-semibold text-ink">{formatBRL(product.sale_price)}</span>
          {product.list_price > product.sale_price && (
            <span className="text-xs text-ink-muted line-through">{formatBRL(product.list_price)}</span>
          )}
        </div>
      </div>
    </motion.button>
  );
}
