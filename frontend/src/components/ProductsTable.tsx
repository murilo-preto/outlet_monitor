import { getCategoryStyle } from "@/lib/categoryStyles";
import { formatBRL } from "@/lib/format";
import { currentPriceColorClass } from "@/lib/priceRange";
import type { Product } from "@/lib/types";

interface ProductsTableProps {
  products: Product[];
}

export function ProductsTable({ products }: ProductsTableProps) {
  const available = products
    .filter((p) => p.currently_listed)
    .sort((a, b) => a.category.localeCompare(b.category) || a.name.localeCompare(b.name));

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
            <th className="px-4 py-3 text-right font-medium">Preço atual</th>
            <th className="px-4 py-3 text-right font-medium">Menor preço</th>
            <th className="px-4 py-3 text-right font-medium">Maior preço</th>
            <th className="px-4 py-3 text-right font-medium">Desconto</th>
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
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
