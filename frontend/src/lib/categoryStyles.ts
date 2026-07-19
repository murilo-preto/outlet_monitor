import {
  Briefcase,
  Building2,
  Gamepad2,
  type LucideIcon,
  RotateCw,
  Sparkles,
  SquareStack,
  Zap,
} from "lucide-react";

// Fixed category -> categorical-slot mapping (color follows the entity, never
// its rank in whatever order the API happens to return). Slots come from the
// dataviz skill's validated 8-hue categorical palette (--color-cat-1..8 in
// globals.css). Class names are spelled out literally (not templated) so
// Tailwind's build-time scanner picks them up.
interface CategoryStyle {
  icon: LucideIcon;
  dotClassName: string;
  textClassName: string;
}

const CATEGORY_STYLES: Record<string, CategoryStyle> = {
  ThinkPad: { icon: Briefcase, dotClassName: "bg-cat-1", textClassName: "text-cat-1" },
  IdeaPad: { icon: Sparkles, dotClassName: "bg-cat-2", textClassName: "text-cat-2" },
  Yoga: { icon: RotateCw, dotClassName: "bg-cat-3", textClassName: "text-cat-3" },
  Legion: { icon: Gamepad2, dotClassName: "bg-cat-4", textClassName: "text-cat-4" },
  LOQ: { icon: Zap, dotClassName: "bg-cat-5", textClassName: "text-cat-5" },
  "V Series": { icon: Building2, dotClassName: "bg-cat-6", textClassName: "text-cat-6" },
  ThinkBook: { icon: SquareStack, dotClassName: "bg-cat-7", textClassName: "text-cat-7" },
};

const FALLBACK_STYLE: CategoryStyle = {
  icon: SquareStack,
  dotClassName: "bg-cat-8",
  textClassName: "text-cat-8",
};

export function getCategoryStyle(category: string): CategoryStyle {
  return CATEGORY_STYLES[category] ?? FALLBACK_STYLE;
}
