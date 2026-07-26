"use client";

import { motion } from "framer-motion";

import { ProductCard } from "./ProductCard";
import { topDeals } from "@/lib/deals";
import type { Product } from "@/lib/types";

interface BestDealsProps {
  products: Product[];
  selectedId: string | null;
  onSelect: (product: Product) => void;
}

export function BestDeals({ products, selectedId, onSelect }: BestDealsProps) {
  const deals = topDeals(products);

  // Nothing to rank yet — on a young database every product scores 0, and an
  // empty "Melhores ofertas" heading would read as a bug.
  if (deals.length === 0) return null;

  return (
    <motion.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="flex flex-col gap-4"
    >
      <div className="flex flex-col gap-1">
        <h2 className="text-lg font-semibold text-ink">Melhores ofertas</h2>
        <p className="text-sm text-ink-secondary">
          Ordenado pela queda em relação ao maior preço já registrado de cada produto, com
          menos peso para os que têm pouco histórico.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {deals.map((product) => (
          <ProductCard
            key={product.product_id}
            product={product}
            selected={product.product_id === selectedId}
            onSelect={onSelect}
            sizeClassName="w-full"
          />
        ))}
      </div>
    </motion.section>
  );
}
