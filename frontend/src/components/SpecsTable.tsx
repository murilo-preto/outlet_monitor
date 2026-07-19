import type { Product } from "@/lib/types";

interface SpecsTableProps {
  specs: Product["specs"];
}

export function SpecsTable({ specs }: SpecsTableProps) {
  if (specs.length === 0) return null;

  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <table className="w-full text-sm">
        <tbody className="divide-y divide-border">
          {specs.map(({ label, value }) => (
            <tr key={label}>
              <td className="w-2/5 bg-surface-raised px-3 py-2 align-top text-ink-secondary">{label}</td>
              <td className="px-3 py-2 text-ink">{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
