import { db } from "./db";
import type { Offer } from "./compute";

const MAX_PRODUCTS = 200;

export async function getOffers(productIds: string[]): Promise<Offer[]> {
  const ids = [...new Set(productIds)].slice(0, MAX_PRODUCTS);
  if (ids.length === 0) return [];

  const { rows } = await db.execute({
    sql: `SELECT product_id, store_id, store_name, store_product_name, url, price, is_available, is_price_outlier
          FROM offers WHERE product_id IN (${ids.map(() => "?").join(", ")})`,
    args: ids,
  });

  return rows.map((r) => ({
    productId: String(r.product_id),
    storeId: Number(r.store_id),
    storeName: String(r.store_name),
    storeProductName: r.store_product_name == null ? null : String(r.store_product_name),
    url: r.url == null ? null : String(r.url),
    price: r.price == null ? null : Number(r.price),
    isAvailable: Number(r.is_available) === 1,
    outlier: Number(r.is_price_outlier) === 1,
  }));
}
