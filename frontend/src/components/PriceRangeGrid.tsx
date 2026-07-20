import { formatBRL } from "@/lib/format";
import { currentPriceColorClass } from "@/lib/priceRange";
import type { Product } from "@/lib/types";

interface PriceRangeGridProps {
  product: Product;
  className?: string;
}

export function PriceRangeGrid({ product, className = "" }: PriceRangeGridProps) {
  const currentColor = currentPriceColorClass(product.sale_price, product.lowest_price, product.highest_price);

  return (
    <div className={`grid grid-cols-2 gap-x-3 gap-y-0.5 font-medium ${className}`}>
      <span className="text-ink-muted">Menor preço</span>
      <span className="text-right text-good">{formatBRL(product.lowest_price)}</span>

      <span className="text-ink-muted">Preço atual</span>
      <span className={`text-right ${currentColor}`}>{formatBRL(product.sale_price)}</span>

      <span className="text-ink-muted">Maior preço</span>
      <span className="text-right text-critical">{formatBRL(product.highest_price)}</span>
    </div>
  );
}
