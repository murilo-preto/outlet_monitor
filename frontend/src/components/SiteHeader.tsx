import { TrendingDown } from "lucide-react";
import Link from "next/link";

interface SiteHeaderProps {
  /** Right-hand actions, which differ per page. */
  children?: React.ReactNode;
}

export function SiteHeader({ children }: SiteHeaderProps) {
  return (
    <header className="header-blur sticky top-0 z-20 border-b border-border backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4">
        <Link href="/" className="flex shrink-0 items-center gap-2 font-semibold text-ink">
          <TrendingDown className="h-5 w-5 text-accent" />
          Outlet Watch
        </Link>
        <div className="flex items-center gap-2 sm:gap-3">{children}</div>
      </div>
    </header>
  );
}
