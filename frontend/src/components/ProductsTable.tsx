"use client";

import { ArrowDown, ArrowUp, ChevronsUpDown } from "lucide-react";
import { useMemo, useState } from "react";

import { getCategoryStyle } from "@/lib/categoryStyles";
import { formatBRL } from "@/lib/format";
import { currentPriceColorClass } from "@/lib/priceRange";
import type { Product } from "@/lib/types";

interface ProductsTableProps {
  products: Product[];
}

type SortKey =
  | "sale_price"
  | "lowest_price"
  | "highest_price"
  | "discount_pct"
  | "deal_score"
  | "ram_gb"
  | "storage_gb";
type SortDirection = "asc" | "desc";

const SORT_COLUMNS: { key: SortKey; label: string }[] = [
  { key: "ram_gb", label: "RAM" },
  { key: "storage_gb", label: "Disco" },
  { key: "sale_price", label: "Preço atual" },
  { key: "lowest_price", label: "Menor preço" },
  { key: "highest_price", label: "Maior preço" },
  { key: "discount_pct", label: "Desconto" },
  { key: "deal_score", label: "Oferta" },
];

/**
 * Sorts nulls to the end regardless of direction.
 *
 * ram_gb and storage_gb are nullable, and the obvious `(a[key] - b[key]) * sign`
 * yields NaN for those rows — which every comparison treats as false, leaving
 * the array in an arbitrary order rather than merely misplacing the nulls.
 */
function compareBy(key: SortKey, direction: SortDirection) {
  const sign = direction === "asc" ? 1 : -1;
  return (a: Product, b: Product): number => {
    const left = a[key];
    const right = b[key];
    if (left === null && right === null) return 0;
    if (left === null) return 1;
    if (right === null) return -1;
    return (left - right) * sign;
  };
}

export function ProductsTable({ products }: ProductsTableProps) {
  const [sortKey, setSortKey] = useState<SortKey | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDirection((direction) => (direction === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDirection("asc");
    }
  }

  const available = useMemo(() => {
    // filter() returns a fresh array, so the in-place sort never touches the prop.
    const listed = products.filter((p) => p.currently_listed);
    if (sortKey) {
      return listed.sort(compareBy(sortKey, sortDirection));
    }
    return listed.sort((a, b) => a.category.localeCompare(b.category) || a.name.localeCompare(b.name));
  }, [products, sortKey, sortDirection]);

  if (available.length === 0) {
    return (
      <div className="rounded-2xl border border-border p-10 text-center text-sm text-ink-muted">
        Nenhum produto disponível no outlet no momento.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-2xl border border-border bg-surface">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead>
          <tr className="border-b border-border text-xs text-ink-muted">
            <th className="px-4 py-3 font-medium">Produto</th>
            <th className="px-4 py-3 font-medium">Categoria</th>
            {SORT_COLUMNS.map(({ key, label }) => {
              const isActive = sortKey === key;
              return (
                <th key={key} className="px-4 py-3 text-right font-medium">
                  <button
                    type="button"
                    onClick={() => handleSort(key)}
                    className={`flex w-full items-center justify-end gap-1 transition-colors hover:text-ink ${
                      isActive ? "text-ink" : "text-ink-muted"
                    }`}
                  >
                    {label}
                    {isActive ? (
                      sortDirection === "asc" ? (
                        <ArrowUp className="h-3 w-3" />
                      ) : (
                        <ArrowDown className="h-3 w-3" />
                      )
                    ) : (
                      <ChevronsUpDown className="h-3 w-3 opacity-50" />
                    )}
                  </button>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {available.map((product) => {
            const style = getCategoryStyle(product.category);
            const currentColor = currentPriceColorClass(
              product.sale_price,
              product.lowest_price,
              product.highest_price
            );
            return (
              <tr key={product.product_id} className="border-b border-border last:border-0">
                <td className="max-w-xs truncate px-4 py-3 font-medium text-ink">{product.name}</td>
                <td className="px-4 py-3">
                  <span className="flex items-center gap-1.5 whitespace-nowrap text-ink-secondary">
                    <span className={`h-1.5 w-1.5 rounded-full ${style.dotClassName}`} />
                    {product.category}
                  </span>
                </td>
                <td className="px-4 py-3 text-right whitespace-nowrap text-ink-muted">
                  {product.ram_gb !== null ? `${product.ram_gb} GB` : "—"}
                </td>
                <td className="px-4 py-3 text-right whitespace-nowrap text-ink-muted">
                  {product.storage_gb === null
                    ? "—"
                    : product.storage_gb >= 1024
                      ? `${product.storage_gb / 1024} TB`
                      : `${product.storage_gb} GB`}
                </td>
                <td className={`px-4 py-3 text-right font-medium whitespace-nowrap ${currentColor}`}>
                  {formatBRL(product.sale_price)}
                </td>
                <td className="px-4 py-3 text-right whitespace-nowrap text-ink-muted">
                  {formatBRL(product.lowest_price)}
                </td>
                <td className="px-4 py-3 text-right whitespace-nowrap text-ink-muted">
                  {formatBRL(product.highest_price)}
                </td>
                <td className="px-4 py-3 text-right whitespace-nowrap text-ink-muted">
                  {product.discount_pct > 0 ? `${Math.round(product.discount_pct)}%` : "—"}
                </td>
                <td className="px-4 py-3 text-right whitespace-nowrap">
                  {product.deal_score > 0 ? (
                    <span className="font-medium text-good">{product.deal_score}</span>
                  ) : (
                    <span className="text-ink-muted">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
