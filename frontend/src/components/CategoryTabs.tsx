"use client";

import { motion } from "framer-motion";

import { getCategoryStyle } from "@/lib/categoryStyles";
import type { CategoryCount } from "@/lib/types";

interface CategoryTabsProps {
  categories: CategoryCount[];
  selected: string | null;
  onSelect: (category: string) => void;
}

export function CategoryTabs({ categories, selected, onSelect }: CategoryTabsProps) {
  return (
    <div className="no-scrollbar flex gap-2 overflow-x-auto pb-2">
      {categories.map(({ category, product_count }) => {
        const isActive = category === selected;
        const style = getCategoryStyle(category);
        return (
          <button
            key={category}
            onClick={() => onSelect(category)}
            className={`relative flex shrink-0 items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition-colors ${
              isActive
                ? "border-transparent text-accent-ink"
                : "border-border bg-surface text-ink-secondary"
            }`}
          >
            {isActive && (
              <motion.span
                layoutId="category-pill"
                className="absolute inset-0 rounded-full bg-accent"
                transition={{ type: "spring", stiffness: 400, damping: 32 }}
              />
            )}
            <span
              className={`relative z-10 h-2 w-2 shrink-0 rounded-full ${
                isActive ? "bg-accent-ink" : style.dotClassName
              }`}
            />
            <span className="relative z-10 whitespace-nowrap">{category}</span>
            <span
              className="relative z-10 whitespace-nowrap text-xs opacity-70"
              aria-label={`${product_count} products`}
            >
              {product_count}
            </span>
          </button>
        );
      })}
    </div>
  );
}
