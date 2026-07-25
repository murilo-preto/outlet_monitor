import { proxyToApi } from "@/lib/apiProxy";

// Hit directly by the browser as a download link, so the CSV (and its
// Content-Disposition filename) is passed straight through untouched.
export async function GET() {
  return proxyToApi("/export.csv");
}
