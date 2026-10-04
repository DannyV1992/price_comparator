// Cálculo de la comparación. No toca la base de datos: lo usa el navegador con los precios que trae la API.

export type Offer = {
  productId: string;
  storeId: number;
  storeName: string;
  storeProductName: string | null;
  url: string | null;
  price: number | null;
  isAvailable: boolean;
  outlier: boolean;
};

export type Substitute = { productId: string; name: string };

export type Wanted = {
  productId: string;
  name: string;
  qty: number;
  subs?: Record<string, Substitute>; // id de la tienda -> reemplazo en esa tienda
};

export type UsableOffer = Offer & { price: number };

// Lo que se ve en cada celda de la tabla (un producto en una tienda).
export type Cell =
  | { status: "price"; offer: UsableOffer; substitute?: Substitute } // con substitute, el precio es el del reemplazo
  | { status: "out"; substitute?: Substitute } // agotado (con substitute: el reemplazo también está agotado)
  | { status: "none" }; // la tienda no lo vende

export type Row = {
  item: Wanted;
  cells: Map<number, Cell>; // por tienda
  minPrice: number | null; // el precio más bajo del producto elegido (sin contar reemplazos)
  outlier: boolean;
};

export type StoreTotal = {
  storeId: number;
  storeName: string;
  covered: number; // cuántos productos de la lista tiene (contando reemplazos)
  substituted: number; // de esos, cuántos son un reemplazo
  total: number; // suma solo de esos productos
};

export type Comparison = {
  rows: Row[];
  stores: StoreTotal[];
  bestComplete: StoreTotal | null; // la tienda más barata entre las que tienen todo
  split: { total: number; missing: number }; // comprando lo más barato de cada producto donde esté
};

// Un precio de 0 o un producto sin existencias no cuenta como disponible.
export const isUsable = (o: Offer | undefined): o is UsableOffer =>
  !!o && o.isAvailable && o.price != null && o.price > 0;

// `allStores` son las tiendas que se muestran como columna, aunque no tengan nada de la lista.
export function buildComparison(
  items: Wanted[],
  offers: Offer[],
  allStores: { id: number; name: string }[] = [],
): Comparison {
  const byProduct = new Map<string, Map<number, Offer>>();
  const storeNames = new Map<number, string>(allStores.map((s) => [s.id, s.name]));
  for (const o of offers) {
    storeNames.set(o.storeId, o.storeName);
    if (!byProduct.has(o.productId)) byProduct.set(o.productId, new Map());
    byProduct.get(o.productId)!.set(o.storeId, o);
  }

  const rows: Row[] = items.map((item) => {
    const own = byProduct.get(item.productId) ?? new Map<number, Offer>();
    const cells = new Map<number, Cell>();
    for (const storeId of storeNames.keys()) {
      const original = own.get(storeId);
      if (isUsable(original)) {
        cells.set(storeId, { status: "price", offer: original });
        continue;
      }
      // El producto elegido no está disponible aquí: se usa el reemplazo, si hay uno.
      const substitute = item.subs?.[String(storeId)];
      if (!substitute) {
        cells.set(storeId, original ? { status: "out" } : { status: "none" });
        continue;
      }
      const replacement = byProduct.get(substitute.productId)?.get(storeId);
      cells.set(
        storeId,
        isUsable(replacement) ? { status: "price", offer: replacement, substitute } : { status: "out", substitute },
      );
    }

    const prices = [...cells.values()].flatMap((c) => (c.status === "price" && !c.substitute ? [c.offer.price] : []));
    return {
      item,
      cells,
      minPrice: prices.length ? Math.min(...prices) : null,
      outlier: [...own.values()].some((o) => o.outlier),
    };
  });

  const stores: StoreTotal[] = [...storeNames].map(([storeId, storeName]) => {
    let covered = 0;
    let substituted = 0;
    let total = 0;
    for (const row of rows) {
      const cell = row.cells.get(storeId);
      if (cell?.status === "price") {
        covered += 1;
        if (cell.substitute) substituted += 1;
        total += cell.offer.price * row.item.qty;
      }
    }
    return { storeId, storeName, covered, substituted, total };
  });
  // Primero las tiendas que tienen más productos de la lista; entre ellas, la más barata.
  stores.sort((a, b) => b.covered - a.covered || a.total - b.total);

  const complete = stores.filter((s) => s.covered === rows.length);
  const bestComplete = rows.length > 0 && complete.length ? complete.reduce((a, b) => (b.total < a.total ? b : a)) : null;

  // "Lo más barato de cada producto" solo usa el producto elegido: un reemplazo es otro producto.
  let splitTotal = 0;
  let missing = 0;
  for (const row of rows) {
    if (row.minPrice == null) missing += 1;
    else splitTotal += row.minPrice * row.item.qty;
  }

  return { rows, stores, bestComplete, split: { total: splitTotal, missing } };
}
