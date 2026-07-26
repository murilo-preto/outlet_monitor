"use client";

import { Search, X } from "lucide-react";

import { formatBRL } from "@/lib/format";
import {
  DEFAULT_FILTERS,
  hasActiveFilters,
  type FilterOptions,
  type ProductFilters as Filters,
} from "@/lib/productFilter";

interface ProductFiltersProps {
  filters: Filters;
  options: FilterOptions;
  onChange: (filters: Filters) => void;
  matchCount: number;
  totalCount: number;
}

const selectClass =
  "rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-accent";

export function ProductFilters({
  filters,
  options,
  onChange,
  matchCount,
  totalCount,
}: ProductFiltersProps) {
  const set = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    onChange({ ...filters, [key]: value });

  // "" is the empty option; every real value is a positive number.
  const toNumber = (value: string) => (value === "" ? null : Number(value));

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-border bg-surface p-4">
      <div className="flex flex-wrap items-center gap-3">
        <label className="relative flex min-w-[220px] flex-1 items-center">
          <Search className="pointer-events-none absolute left-3 h-4 w-4 text-ink-muted" />
          <input
            type="search"
            value={filters.search}
            onChange={(e) => set("search", e.target.value)}
            placeholder="Buscar por nome ou processador"
            aria-label="Buscar produtos"
            className={`${selectClass} w-full pl-9`}
          />
        </label>

        <select
          value={filters.minRamGb ?? ""}
          onChange={(e) => set("minRamGb", toNumber(e.target.value))}
          aria-label="Memória mínima"
          className={selectClass}
        >
          <option value="">Memória</option>
          {options.ramValues.map((gb) => (
            <option key={gb} value={gb}>
              {gb} GB ou mais
            </option>
          ))}
        </select>

        <select
          value={filters.minStorageGb ?? ""}
          onChange={(e) => set("minStorageGb", toNumber(e.target.value))}
          aria-label="Armazenamento mínimo"
          className={selectClass}
        >
          <option value="">Armazenamento</option>
          {options.storageValues.map((gb) => (
            <option key={gb} value={gb}>
              {gb >= 1024 ? `${gb / 1024} TB` : `${gb} GB`} ou mais
            </option>
          ))}
        </select>

        <select
          value={filters.maxPrice ?? ""}
          onChange={(e) => set("maxPrice", toNumber(e.target.value))}
          aria-label="Preço máximo"
          className={selectClass}
        >
          <option value="">Preço</option>
          {priceSteps(options.priceMax).map((price) => (
            <option key={price} value={price}>
              Até {formatBRL(price)}
            </option>
          ))}
        </select>

        <label className="flex cursor-pointer items-center gap-2 text-sm text-ink-secondary">
          <input
            type="checkbox"
            checked={filters.discreteGpuOnly}
            onChange={(e) => set("discreteGpuOnly", e.target.checked)}
            className="h-4 w-4 accent-[var(--color-accent)]"
          />
          Placa dedicada
        </label>
      </div>

      <div className="flex items-center gap-3 text-xs text-ink-muted">
        <span>
          {matchCount} de {totalCount} produtos
        </span>
        {hasActiveFilters(filters) && (
          <button
            type="button"
            onClick={() => onChange(DEFAULT_FILTERS)}
            className="flex items-center gap-1 font-medium text-accent"
          >
            <X className="h-3 w-3" />
            Limpar filtros
          </button>
        )}
      </div>
    </div>
  );
}

/** Round thousands up to the catalogue's ceiling, so every step matches something. */
function priceSteps(priceMax: number): number[] {
  const steps: number[] = [];
  for (let price = 2000; price < priceMax; price += 2000) steps.push(price);
  return steps;
}
