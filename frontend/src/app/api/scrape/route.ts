import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { proxyToApi } from "@/lib/apiProxy";

// Only this route is gated — GET routes stay open since they just serve
// Lenovo's public price data. If SCRAPE_SECRET isn't set (local dev), the
// check is skipped entirely so `docker compose up` keeps working with zero
// extra config; production sets it via .env.prod.
export async function POST(request: NextRequest) {
  const requiredSecret = process.env.SCRAPE_SECRET;
  if (requiredSecret) {
    const provided = request.headers.get("x-scrape-token");
    if (provided !== requiredSecret) {
      return NextResponse.json({ error: "invalid or missing scrape token" }, { status: 401 });
    }
  }

  return proxyToApi("/scrape", { method: "POST" });
}
