import { proxyToApi } from "@/lib/apiProxy";

export async function GET() {
  return proxyToApi("/categories");
}
