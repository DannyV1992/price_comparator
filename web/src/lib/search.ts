import { db } from "./db";

export type StoreOffer = {
  storeName: string;
  price: number | null;
  available: boolean; // con existencias y con un precio mayor que 0
};

export type ProductHit = {
  productId: string;
  name: string;
  brand: string | null;
  imageUrl: string | null;
  nStores: number;
  minPrice: number | null;
  minStore: string | null;
  priceOutlier: boolean;
  offers: StoreOffer[];
};

// Un producto de una tienda concreta, para elegirlo como reemplazo de uno agotado.
export type StoreHit = {
  productId: string;
  name: string;
  brand: string | null;
  imageUrl: string | null;
  storeProductName: string | null;
  price: number;
  url: string | null;
};

const LIMIT = 30;

// Convierte lo que escribe la persona en una consulta FTS5: cada palabra es un prefijo y todas deben aparecer.
function toFtsQuery(text: string): string | null {
  const words = text.match(/[\p{L}\p{N}]+/gu);
  if (!words) return null;
  return words.map((w) => `"${w}"*`).join(" ");
}

const str = (v: unknown) => (v == null ? null : String(v));

export type Store = { id: number; name: string };

export async function getStores(): Promise<Store[]> {
  const { rows } = await db.execute("SELECT DISTINCT store_id, store_name FROM offers ORDER BY store_name");
  return rows.map((r) => ({ id: Number(r.store_id), name: String(r.store_name) }));
}

// Con storeIds, solo salen los productos que alguna de esas tiendas tiene con existencias, y el
// «desde» se calcula entre esas tiendas.
export async function searchProducts(text: string, storeIds: number[] = []): Promise<ProductHit[]> {
  const match = toFtsQuery(text);
  if (!match) return [];

  const marks = storeIds.map(() => "?").join(", ");
  const inStores = storeIds.length ? `AND o.store_id IN (${marks})` : "";
  const sold = storeIds.length
    ? `AND EXISTS (SELECT 1 FROM offers o WHERE o.product_id = p.product_id AND o.store_id IN (${marks})
                     AND o.is_available = 1 AND o.price > 0)`
    : "";

  // Primero los productos que se venden en más tiendas: son los que sirven para comparar.
  // Los argumentos van en el mismo orden en que aparecen los «?» en el texto.
  const { rows } = await db.execute({
    sql: `SELECT p.product_id, p.name, p.brand, p.image_url, p.n_stores,
                 (SELECT o.price FROM offers o
                   WHERE o.product_id = p.product_id AND o.is_available = 1 AND o.price > 0 ${inStores}
                   ORDER BY o.price LIMIT 1) AS min_price,
                 (SELECT o.store_name FROM offers o
                   WHERE o.product_id = p.product_id AND o.is_available = 1 AND o.price > 0 ${inStores}
                   ORDER BY o.price LIMIT 1) AS min_store,
                 (SELECT MAX(o.is_price_outlier) FROM offers o WHERE o.product_id = p.product_id) AS outlier
          FROM products_fts f JOIN products p ON p.rowid = f.rowid
          WHERE products_fts MATCH ? ${sold}
          ORDER BY p.n_stores DESC, f.rank
          LIMIT ${LIMIT}`,
    args: [...storeIds, ...storeIds, match, ...storeIds],
  });
  if (rows.length === 0) return [];

  // Las tiendas de cada resultado, para el cuadro que aparece al pasar el mouse.
  const ids = rows.map((r) => String(r.product_id));
  const { rows: offerRows } = await db.execute({
    sql: `SELECT product_id, store_name, price, is_available FROM offers
          WHERE product_id IN (${ids.map(() => "?").join(", ")})`,
    args: ids,
  });
  const byProduct = new Map<string, StoreOffer[]>();
  for (const o of offerRows) {
    const price = o.price == null ? null : Number(o.price);
    const offer: StoreOffer = {
      storeName: String(o.store_name),
      price,
      available: Number(o.is_available) === 1 && price != null && price > 0,
    };
    const id = String(o.product_id);
    byProduct.set(id, [...(byProduct.get(id) ?? []), offer]);
  }
  // Con existencias primero y de más barato a más caro; los agotados al final.
  for (const list of byProduct.values()) {
    list.sort((a, b) => Number(b.available) - Number(a.available) || (a.price ?? 0) - (b.price ?? 0));
  }

  return rows.map((r) => ({
    productId: String(r.product_id),
    name: String(r.name),
    brand: str(r.brand),
    imageUrl: str(r.image_url),
    nStores: Number(r.n_stores),
    minPrice: r.min_price == null ? null : Number(r.min_price),
    minStore: str(r.min_store),
    priceOutlier: Number(r.outlier) === 1,
    offers: byProduct.get(String(r.product_id)) ?? [],
  }));
}

// Busca entre lo que vende una tienda y tiene existencias.
export async function searchStoreProducts(text: string, storeId: number): Promise<StoreHit[]> {
  const match = toFtsQuery(text);
  if (!match) return [];

  const { rows } = await db.execute({
    sql: `SELECT p.product_id, p.name, p.brand, p.image_url, o.store_product_name, o.price, o.url
          FROM products_fts f
          JOIN products p ON p.rowid = f.rowid
          JOIN offers o ON o.product_id = p.product_id
          WHERE products_fts MATCH ? AND o.store_id = ? AND o.is_available = 1 AND o.price > 0
          ORDER BY f.rank
          LIMIT ${LIMIT}`,
    args: [match, storeId],
  });

  return rows.map((r) => ({
    productId: String(r.product_id),
    name: String(r.name),
    brand: str(r.brand),
    imageUrl: str(r.image_url),
    storeProductName: str(r.store_product_name),
    price: Number(r.price),
    url: str(r.url),
  }));
}
