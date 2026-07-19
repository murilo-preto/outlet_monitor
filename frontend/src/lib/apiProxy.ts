import { NextResponse } from "next/server";

// Server-only: the Flask API is reachable only over the internal Docker
// network (never publishes a host port), so every browser-facing data call
// goes through a Route Handler that forwards here.
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://api:5000";

export async function proxyToApi(path: string, init?: RequestInit): Promise<NextResponse> {
  const res = await fetch(`${API_INTERNAL_URL}${path}`, init);
  const body = await res.text();
  return new NextResponse(body, {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
  });
}
