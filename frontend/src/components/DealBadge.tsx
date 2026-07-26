import { Flame, TrendingDown } from "lucide-react";

import { hasNotableDrop } from "@/lib/deals";
import type { Product } from "@/lib/types";

interface DealBadgeProps {
  product: Product;
  className?: string;
}

/**
 * A record-low or off-peak marker, or nothing at all.
 *
 * `at_all_time_low === null` means the product has too little price history to
 * judge, and deliberately renders nothing — an absent badge reads as "no claim
 * made", which is the truth. Showing a "not a record" state would instead be
 * asserting something the data cannot support.
 */
export function DealBadge({ product, className = "" }: DealBadgeProps) {
  const base = `inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${className}`;

  if (product.at_all_time_low === true) {
    return (
      <span className={`${base} bg-good text-white`}>
        <Flame className="h-3 w-3" />
        Menor preço histórico
      </span>
    );
  }

  if (hasNotableDrop(product)) {
    return (
      <span className={`${base} bg-surface-raised text-good`}>
        <TrendingDown className="h-3 w-3" />
        {Math.round(product.pct_below_high)}% abaixo do pico
      </span>
    );
  }

  return null;
}
