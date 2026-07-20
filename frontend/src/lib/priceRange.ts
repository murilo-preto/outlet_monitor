export function currentPriceColorClass(current: number, lowest: number, highest: number): string {
  if (lowest === highest || current <= lowest) return "text-good";
  if (current >= highest) return "text-critical";
  return "text-warning";
}
