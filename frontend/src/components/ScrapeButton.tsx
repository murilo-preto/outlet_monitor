"use client";

import { motion } from "framer-motion";
import { RefreshCw } from "lucide-react";
import { useState } from "react";

import { ScrapeAuthError, triggerScrape } from "@/lib/api";

const TOKEN_STORAGE_KEY = "outlet-monitor-scrape-token";

interface ScrapeButtonProps {
  onDone: () => void;
}

export function ScrapeButton({ onDone }: ScrapeButtonProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setLoading(true);
    setError(null);
    try {
      const storedToken = localStorage.getItem(TOKEN_STORAGE_KEY) ?? undefined;
      try {
        await triggerScrape(storedToken);
      } catch (err) {
        if (!(err instanceof ScrapeAuthError)) throw err;

        const entered = window.prompt("Senha para atualizar preços:");
        if (!entered) {
          throw new Error("Atualização cancelada");
        }
        await triggerScrape(entered);
        localStorage.setItem(TOKEN_STORAGE_KEY, entered);
      }
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao buscar dados");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <motion.button
        onClick={handleClick}
        disabled={loading}
        whileHover={{ scale: loading ? 1 : 1.03 }}
        whileTap={{ scale: loading ? 1 : 0.97 }}
        className="flex items-center gap-2 rounded-full bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-60"
      >
        <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        {loading ? "Buscando..." : "Atualizar preços"}
      </motion.button>
      {error && <span className="text-xs text-critical">{error}</span>}
    </div>
  );
}
