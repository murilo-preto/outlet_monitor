import type { NextRequest } from "next/server";

import { proxyToApi } from "@/lib/apiProxy";

export async function GET(request: NextRequest) {
  const category = request.nextUrl.searchParams.get("category");
  const query = category ? `?category=${encodeURIComponent(category)}` : "";
  return proxyToApi(`/products${query}`);
}
