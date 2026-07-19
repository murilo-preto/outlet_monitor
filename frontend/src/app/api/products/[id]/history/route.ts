import { proxyToApi } from "@/lib/apiProxy";

export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return proxyToApi(`/products/${encodeURIComponent(id)}/history`);
}
