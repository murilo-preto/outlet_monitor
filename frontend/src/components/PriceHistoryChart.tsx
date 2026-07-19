"use client";

import { Clock } from "lucide-react";
import { useSyncExternalStore } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatBRL, formatDate, formatDateTime } from "@/lib/format";
import type { Product } from "@/lib/types";

const ACCENT = { light: "#2a78d6", dark: "#3987e5" };
const GRIDLINE = { light: "#e1e0d9", dark: "#2c2c2a" };
const MUTED = "#898781";

function subscribeToColorScheme(callback: () => void) {
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  mq.addEventListener("change", callback);
  return () => mq.removeEventListener("change", callback);
}

function getIsDarkSnapshot() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function useIsDark(): boolean {
  return useSyncExternalStore(subscribeToColorScheme, getIsDarkSnapshot, () => false);
}

interface TooltipPayloadEntry {
  value: number;
  payload: { timestamp: string };
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayloadEntry[] }) {
  if (!active || !payload?.length) return null;
  const point = payload[0];
  return (
    <div className="rounded-lg border border-border bg-surface-raised px-3 py-2 text-sm shadow-lg">
      <div className="text-xs text-ink-muted">{formatDateTime(point.payload.timestamp)}</div>
      <div className="font-semibold text-ink">{formatBRL(point.value)}</div>
    </div>
  );
}

interface PriceHistoryChartProps {
  history: Product[];
}

export function PriceHistoryChart({ history }: PriceHistoryChartProps) {
  const isDark = useIsDark();
  const accent = isDark ? ACCENT.dark : ACCENT.light;
  const gridline = isDark ? GRIDLINE.dark : GRIDLINE.light;

  if (history.length < 2) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-border py-16 text-center text-ink-muted">
        <Clock className="h-6 w-6" />
        <p className="text-sm">
          Ainda não há histórico suficiente para este produto.
          <br />
          Rode um novo scrape em outro dia para começar a ver a tendência.
        </p>
      </div>
    );
  }

  const data = history.map((snapshot) => ({
    timestamp: snapshot.timestamp,
    price: snapshot.sale_price,
  }));

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={accent} stopOpacity={0.1} />
              <stop offset="100%" stopColor={accent} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke={gridline} strokeWidth={1} />
          <XAxis
            dataKey="timestamp"
            tickFormatter={formatDate}
            tick={{ fill: MUTED, fontSize: 12 }}
            axisLine={{ stroke: gridline }}
            tickLine={false}
          />
          <YAxis
            tickFormatter={(value: number) => formatBRL(value)}
            tick={{ fill: MUTED, fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={90}
          />
          <Tooltip content={<ChartTooltip />} cursor={{ stroke: gridline, strokeWidth: 1 }} />
          <Area
            type="monotone"
            dataKey="price"
            stroke={accent}
            strokeWidth={2}
            fill="url(#priceFill)"
            dot={{ r: 4, fill: accent, stroke: "var(--color-surface)", strokeWidth: 2 }}
            activeDot={{ r: 5, fill: accent, stroke: "var(--color-surface)", strokeWidth: 2 }}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
