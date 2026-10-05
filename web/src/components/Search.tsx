"use client";

import { useEffect, useState } from "react";
import { addItem, useList } from "@/lib/list";
import { formatPrice } from "@/lib/format";
import type { ProductHit, Store } from "@/lib/search";
import { StoreChips } from "./StoreChips";
import { Thumb } from "./Thumb";

export function Search() {
  const [query, setQuery] = useState("");
  const [stores, setStores] = useState<Store[]>([]);
  const [selected, setSelected] = useState<number[]>([]); // vacío = todas las tiendas
  const [result, setResult] = useState<{ key: string; products: ProductHit[]; hasMore: boolean }>({
    key: "",
    products: [],
    hasMore: false,
  });
  const [loadingMore, setLoadingMore] = useState(false);
  const list = useList();
  const text = query.trim();
  const filter = [...selected].sort((a, b) => a - b).join(",");
  const key = `${text}|${filter}`;

  useEffect(() => {
    fetch("/api/stores")
      .then((res) => res.json() as Promise<{ stores: Store[] }>)
      .then((data) => setStores(data.stores))
      .catch(() => {}); // sin la lista de tiendas la búsqueda funciona igual, solo sin filtro
  }, []);

  useEffect(() => {
    if (!text) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const url = `/api/search?q=${encodeURIComponent(text)}${filter ? `&stores=${filter}` : ""}`;
        const res = await fetch(url, { signal: controller.signal });
        const data = (await res.json()) as { products: ProductHit[]; hasMore: boolean };
        setResult({ key: `${text}|${filter}`, products: data.products, hasMore: data.hasMore });
      } catch {
        // búsqueda cancelada por una más nueva
      }
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [text, filter]);

  // «Ver más»: pide la siguiente página y la agrega al final.
  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const url = `/api/search?q=${encodeURIComponent(text)}${filter ? `&stores=${filter}` : ""}&offset=${products.length}`;
      const data = (await (await fetch(url)).json()) as { products: ProductHit[]; hasMore: boolean };
      setResult((cur) =>
        cur.key !== key
          ? cur // la búsqueda cambió mientras llegaba la página
          : {
              ...cur,
              products: [
                ...cur.products,
                ...data.products.filter((p) => !cur.products.some((q) => q.productId === p.productId)),
              ],
              hasMore: data.hasMore,
            },
      );
    } finally {
      setLoadingMore(false);
    }
  };
  const toggle = (id: number) => setSelected((cur) => (cur.includes(id) ? cur.filter((s) => s !== id) : [...cur, id]));
  const loading = text !== "" && result.key !== key;
  const products = text ? result.products : [];
  const inList = new Map(list.map((i) => [i.productId, i.qty]));

  return (
    <section>
      <input
        className="search"
        type="search"
        placeholder="Busca un producto: arroz, leche, café..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        autoFocus
      />
      {stores.length > 0 && (
        <StoreChips
          label="Ver solo lo que tiene:"
          stores={stores}
          isOn={(id) => selected.includes(id)}
          onToggle={toggle}
          onAll={{ label: "Todos", active: selected.length === 0, run: () => setSelected([]) }}
        />
      )}
      {loading && <p className="hint">Buscando...</p>}
      {!loading && text && products.length === 0 && (
        <p className="hint">
          Sin resultados para «{text}»{selected.length > 0 && " en los supermercados elegidos"}.
        </p>
      )}
      <ul className="results">
        {products.map((p) => {
          const qty = inList.get(p.productId);
          return (
            <li key={p.productId} className="card">
              <Thumb src={p.imageUrl} alt={p.name} />
              <div className="info">
                <strong>{p.name}</strong>
                <span className="meta">
                  {p.brand ? `${p.brand} · ` : ""}
                  <span className="stores" tabIndex={0}>
                    {p.nStores === 1 ? "1 supermercado" : `${p.nStores} supermercados`}
                    <span className="tip" role="tooltip">
                      {p.offers.map((o) => (
                        <span key={o.storeName} className={o.available ? "tip-row" : "tip-row off"}>
                          <span>{o.storeName}</span>
                          <b>{o.available && o.price != null ? formatPrice(o.price) : "Agotado"}</b>
                        </span>
                      ))}
                    </span>
                  </span>
                </span>
                {p.minPrice != null ? (
                  <span className="meta">
                    Desde <b>{formatPrice(p.minPrice)}</b> en {p.minStore}
                    {p.priceOutlier && <em className="warn"> · precios muy distintos, revisa</em>}
                  </span>
                ) : (
                  <span className="meta">Sin existencias ahora</span>
                )}
              </div>
              <button
                className={qty ? "add added" : "add"}
                onClick={() => addItem({ productId: p.productId, name: p.name, brand: p.brand, imageUrl: p.imageUrl })}
              >
                {qty ? `En la lista (${qty}) +` : "Agregar"}
              </button>
            </li>
          );
        })}
      </ul>
      {!loading && result.hasMore && products.length > 0 && (
        <button className="secondary more" onClick={loadMore} disabled={loadingMore}>
          {loadingMore ? "Cargando..." : "Ver más resultados"}
        </button>
      )}
    </section>
  );
}
