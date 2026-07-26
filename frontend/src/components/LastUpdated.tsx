import { AlertTriangle, Clock } from "lucide-react";

import { formatDateTime, formatDays } from "@/lib/format";
import type { ScrapeStatus } from "@/lib/types";

interface LastUpdatedProps {
  status: ScrapeStatus | null;
}

/**
 * How long ago the data was actually collected.
 *
 * Worth its own indicator because a stalled scraper is otherwise invisible:
 * prices in this outlet rarely move, so "no changes reported" looks identical
 * whether collection is healthy or stopped weeks ago.
 */
export function LastUpdated({ status }: LastUpdatedProps) {
  if (!status) return null;

  const { last_success_at, hours_since_last_success, consecutive_failures, stale } = status;

  if (last_success_at === null || hours_since_last_success === null) {
    return (
      <p className="flex items-center gap-1.5 text-sm text-ink-muted">
        <Clock className="h-3.5 w-3.5" />
        Ainda sem coletas
      </p>
    );
  }

  const failing = consecutive_failures >= 3;
  const tone = failing ? "text-critical" : stale ? "text-warning" : "text-ink-muted";
  const Icon = failing || stale ? AlertTriangle : Clock;

  return (
    <p className={`flex items-center gap-1.5 text-sm ${tone}`} title={formatDateTime(last_success_at)}>
      <Icon className="h-3.5 w-3.5" />
      Atualizado {formatElapsed(hours_since_last_success)}
      {failing && ` · ${consecutive_failures} falhas seguidas`}
    </p>
  );
}

function formatElapsed(hours: number): string {
  if (hours < 1) return "agora há pouco";
  if (hours < 24) {
    const whole = Math.round(hours);
    return whole === 1 ? "há 1 hora" : `há ${whole} horas`;
  }
  return `há ${formatDays(hours / 24)}`;
}
