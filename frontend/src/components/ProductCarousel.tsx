"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import useEmblaCarousel from "embla-carousel-react";

import { ProductCard } from "./ProductCard";
import type { Product } from "@/lib/types";

interface ProductCarouselProps {
  products: Product[];
  selectedId: string | null;
  onSelect: (product: Product) => void;
}

export function ProductCarousel({ products, selectedId, onSelect }: ProductCarouselProps) {
  const [emblaRef, emblaApi] = useEmblaCarousel({ align: "start", dragFree: true, containScroll: "trimSnaps" });
  const [canScrollPrev, setCanScrollPrev] = useState(false);
  const [canScrollNext, setCanScrollNext] = useState(false);

  const updateButtons = useCallback(() => {
    if (!emblaApi) return;
    setCanScrollPrev(emblaApi.canScrollPrev());
    setCanScrollNext(emblaApi.canScrollNext());
  }, [emblaApi]);

  useEffect(() => {
    if (!emblaApi) return;
    // Seed initial button state, then subscribe to embla's own event emitter
    // for updates — the standard embla-carousel-react integration pattern.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    updateButtons();
    emblaApi.on("select", updateButtons);
    emblaApi.on("reInit", updateButtons);
  }, [emblaApi, updateButtons]);

  return (
    <div className="relative">
      <div className="overflow-hidden" ref={emblaRef}>
        <div className="flex gap-4 py-2">
          <AnimatePresence initial={false}>
            {products.map((product, index) => (
              <motion.div
                key={product.product_id}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: Math.min(index * 0.04, 0.4) }}
              >
                <ProductCard
                  product={product}
                  selected={product.product_id === selectedId}
                  onSelect={onSelect}
                />
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      </div>

      {canScrollPrev && (
        <button
          aria-label="Anterior"
          onClick={() => emblaApi?.scrollPrev()}
          className="absolute top-1/2 -left-3 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-surface-raised shadow-sm"
        >
          <ChevronLeft className="h-4 w-4 text-ink" />
        </button>
      )}
      {canScrollNext && (
        <button
          aria-label="Próximo"
          onClick={() => emblaApi?.scrollNext()}
          className="absolute top-1/2 -right-3 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-surface-raised shadow-sm"
        >
          <ChevronRight className="h-4 w-4 text-ink" />
        </button>
      )}
    </div>
  );
}
