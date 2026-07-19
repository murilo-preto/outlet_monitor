interface StatTileProps {
  label: string;
  value: string;
}

export function StatTile({ label, value }: StatTileProps) {
  return (
    <div className="flex flex-col gap-1 rounded-2xl border border-border bg-surface px-5 py-4">
      <span className="text-xs text-ink-muted">{label}</span>
      <span className="text-2xl font-semibold text-ink">{value}</span>
    </div>
  );
}
