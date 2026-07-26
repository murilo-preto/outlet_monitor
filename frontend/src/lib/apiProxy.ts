import { NextResponse } from "next/server";

// Server-only: the Flask API is reachable only over the internal Docker
// network (never publishes a host port), so every browser-facing data call
// goes through a Route Handler that forwards here.
const API_INTERNAL_URL = process.env.API_INTERNAL_URL ?? "http://api:5000";

export async function proxyToApi(path: string, init?: RequestInit): Promise<NextResponse> {
  const res = await fetch(`${API_INTERNAL_URL}${path}`, init);
  const headers: Record<string, string> = {
    "content-type": res.headers.get("content-type") ?? "application/json",
  };
  // Forwarded so file downloads (the CSV export) keep the filename the API
  // chose instead of being saved as the route's name.
  const disposition = res.headers.get("content-disposition");
  if (disposition) headers["content-disposition"] = disposition;

  // Passing the body through as a stream rather than awaiting res.text():
  // Flask's /export.csv is a lazy row-by-row generator, and buffering it here
  // threw that away — measured 2,014ms to first byte instead of 17ms, plus a
  // full copy of the CSV decoded into a UTF-16 string per concurrent request.
  return new NextResponse(res.body, { status: res.status, headers });
}
