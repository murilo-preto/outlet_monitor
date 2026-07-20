"use client";

import { motion } from "framer-motion";

import { getCategoryStyle } from "@/lib/categoryStyles";
import type { CategoryCount } from "@/lib/types";

interface CategoryTabsProps {
  categories: CategoryCount[];
  selected: string | null;
  onSelect: (category: string | null) => void;
}

interface TabProps {
  label: string;
  count: number;
  isActive: boolean;
  dotClassName: string;
  onClick: () => void;
}

function Tab({ label, count, isActive, dotClassName, onClick }: TabProps) {
  return (
    <button
      onClick={onClick}
      className={`relative flex shrink-0 grow items-center justify-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition-colors ${
        isActive ? "border-transparent text-accent-ink" : "border-border bg-surface text-ink-secondary"
      }`}
    >
      {isActive && (
        <motion.span
          layoutId="category-pill"
          className="absolute inset-0 rounded-full bg-accent"
          transition={{ type: "spring", stiffness: 400, damping: 32 }}
        />
      )}
      <span className={`relative z-10 h-2 w-2 shrink-0 rounded-full ${isActive ? "bg-accent-ink" : dotClassName}`} />
      <span className="relative z-10 whitespace-nowrap">{label}</span>
      <span className="relative z-10 whitespace-nowrap text-xs opacity-70" aria-label={`${count} products`}>
        {count}
      </span>
    </button>
  );
}

export function CategoryTabs({ categories, selected, onSelect }: CategoryTabsProps) {
  const totalCount = categories.reduce((sum, { product_count }) => sum + product_count, 0);

  return (
    <div className="no-scrollbar flex gap-2 overflow-x-auto pb-2">
      <Tab
        label="Todos"
        count={totalCount}
        isActive={selected === null}
        dotClassName="bg-ink-muted"
        onClick={() => onSelect(null)}
      />
      {categories.map(({ category, product_count }) => (
        <Tab
          key={category}
          label={category}
          count={product_count}
          isActive={category === selected}
          dotClassName={getCategoryStyle(category).dotClassName}
          onClick={() => onSelect(category)}
        />
      ))}
    </div>
  );
}
