import { searchProducts, searchStoreProducts } from "@/lib/search";

// /api/search?q=arroz                 busca en todo el catálogo
// /api/search?q=arroz&stores=1,4      solo lo que tienen esas tiendas con existencias
// /api/search?q=arroz&store=12        lo que tiene esa tienda (para elegir un reemplazo)
export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const q = (params.get("q") ?? "").slice(0, 100);
  const offset = Math.max(0, Math.min(Number(params.get("offset")) || 0, 5000)); // «Ver más»

  if (params.has("store")) {
    const store = Number(params.get("store"));
    if (!Number.isInteger(store)) return Response.json({ products: [], hasMore: false }, { status: 400 });
    return Response.json(await searchStoreProducts(q, store, offset));
  }

  const stores = (params.get("stores") ?? "")
    .split(",")
    .filter((s) => s.trim() !== "") // "".split(",") da [""], y Number("") es 0
    .map(Number)
    .filter((n) => Number.isInteger(n))
    .slice(0, 20);
  return Response.json(await searchProducts(q, stores, offset));
}
