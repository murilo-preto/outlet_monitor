const currencyFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

export function formatBRL(value: number): string {
  return currencyFormatter.format(value);
}

export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
}

/** 0.5 -> "12 horas", 1 -> "1 dia", 7.5 -> "7 dias" (pt-BR, singular-aware). */
export function formatDays(days: number): string {
  if (days < 1) {
    const hours = Math.max(1, Math.round(days * 24));
    return hours === 1 ? "1 hora" : `${hours} horas`;
  }
  const whole = Math.round(days);
  return whole === 1 ? "1 dia" : `${whole} dias`;
}

export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(iso));
}
