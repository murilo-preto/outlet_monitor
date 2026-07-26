import { specsSummary } from "@/lib/specsSummary";
import type { Product } from "@/lib/types";

interface SpecsTableProps {
  product: Product;
}

export function SpecsTable({ product }: SpecsTableProps) {
  const summary = specsSummary(product);

  if (product.specs.length === 0 && summary.length === 0) return null;

  return (
    <div className="flex flex-col gap-3">
      {summary.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {summary.map((chip) => (
            <span
              key={chip}
              className="rounded-full bg-surface-raised px-2.5 py-1 text-xs font-medium text-ink-secondary"
            >
              {chip}
            </span>
          ))}
        </div>
      )}

      {/* The raw table stays: the chips above are a summary, and these carry
          detail (panel type, memory layout, cache) the parser drops. */}
      {product.specs.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-border">
          <table className="w-full text-sm">
            <tbody className="divide-y divide-border">
              {product.specs.map(({ label, value }) => (
                <tr key={label}>
                  <td className="w-2/5 bg-surface-raised px-3 py-2 align-top text-ink-secondary">
                    {label}
                  </td>
                  <td className="px-3 py-2 text-ink">{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
