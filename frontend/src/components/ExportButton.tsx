"use client";

import { motion } from "framer-motion";
import { Download } from "lucide-react";

// A plain link rather than a fetch + blob: the Route Handler already streams
// the file with a Content-Disposition filename, so the browser's own download
// handling is all this needs.
export function ExportButton() {
  return (
    <motion.a
      href="/api/export"
      download
      aria-label="Exportar todos os dados em CSV"
      whileHover={{ scale: 1.03 }}
      whileTap={{ scale: 0.97 }}
      className="flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-2 text-sm font-medium text-ink-secondary transition-colors hover:text-ink sm:px-4"
    >
      <Download className="h-4 w-4" />
      {/* Label collapses on narrow screens, same as the scrape button. */}
      <span className="hidden sm:inline">Exportar CSV</span>
    </motion.a>
  );
}
