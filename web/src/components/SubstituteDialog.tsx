"use client";

import { useEffect, useState } from "react";
import type { Substitute } from "@/lib/list";
import { formatPrice } from "@/lib/format";
import type { StoreHit } from "@/lib/search";
import { Thumb } from "./Thumb";

type Props = {
  itemName: string;
  excludeProductId: string;
  storeId: number;
  storeName: string;
  current?: Substitute;
  available?: boolean; // el producto original sí está disponible en la tienda
  onPick: (sub: Substitute) => void;
  onRemove: () => void;
  onClose: () => void;
};

// Las dos primeras palabras del nombre (p. ej. «Arroz precocido»): un buen punto de partida para buscar algo parecido.
const firstWords = (name: string) => (name.match(/\p{L}+/gu) ?? []).slice(0, 2).join(" ");

export function SubstituteDialog({
  itemName,
  excludeProductId,
  storeId,
  storeName,
  current,
  available,
  onPick,
  onRemove,
  onClose,
}: Props) {
  const [query, setQuery] = useState(() => firstWords(itemName));
  const [qty, setQty] = useState(current?.qty ?? 1); // unidades del reemplazo por cada unidad del original
  const [result, setResult] = useState<{ q: string; products: StoreHit[]; hasMore: boolean }>({
    q: "",
    products: [],
    hasMore: false,
  });
  const [loadingMore, setLoadingMore] = useState(false);
  const text = query.trim();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (!text) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(text)}&store=${storeId}`, {
          signal: controller.signal,
        });
        const data = (await res.json()) as { products: StoreHit[]; hasMore: boolean };
        setResult({ q: text, products: data.products, hasMore: data.hasMore });
      } catch {
        // búsqueda cancelada por una más nueva
      }
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [text, storeId]);

  const loading = text !== "" && result.q !== text;
  const products = (text ? result.products : []).filter((p) => p.productId !== excludeProductId);

  // «Ver más»: pide la siguiente página (el desplazamiento cuenta todo lo ya cargado, también el producto excluido).
  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const res = await fetch(
        `/api/search?q=${encodeURIComponent(text)}&store=${storeId}&offset=${result.products.length}`,
      );
      const data = (await res.json()) as { products: StoreHit[]; hasMore: boolean };
      setResult((cur) =>
        cur.q !== text ? cur : { ...cur, products: [...cur.products, ...data.products], hasMore: data.hasMore },
      );
    } finally {
      setLoadingMore(false);
    }
  };

  return (
    <div className="overlay" onClick={onClose}>
      <div
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-label={`Reemplazar en ${storeName}`}
        onClick={(e) => e.stopPropagation()}
      >
        <h3>Reemplazar en {storeName}</h3>
        <p className="meta">
          {available
            ? `«${itemName}» sí está disponible en ${storeName}, pero puedes usar otro producto en su lugar.`
            : `«${itemName}» no está disponible en ${storeName}.`}{" "}
          Elige un producto parecido que este supermercado tenga; en la tabla quedará marcado como reemplazo.
        </p>
        {current && (
          <p className="meta">
            Reemplazo actual: <b>{current.name}</b>
            {(current.qty ?? 1) > 1 && <> ×{current.qty}</>}
            {qty !== (current.qty ?? 1) && (
              <>
                {" "}
                <button className="clear" onClick={() => onPick({ ...current, qty })}>
                  Guardar la cantidad
                </button>
              </>
            )}
          </p>
        )}
        <label className="qty-pick">
          Unidades del reemplazo por cada «{itemName}»
          <span className="qty">
            <button aria-label="Quitar uno" onClick={() => setQty((q) => Math.max(1, q - 1))}>
              −
            </button>
            <span>{qty}</span>
            <button aria-label="Agregar uno" onClick={() => setQty((q) => q + 1)}>
              +
            </button>
          </span>
        </label>
        <input
          className="search"
          type="search"
          placeholder={`Busca en ${storeName}...`}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoFocus
        />
        <div className="dialog-results">
          {loading && <p className="hint">Buscando...</p>}
          {!loading && text && products.length === 0 && (
            <p className="hint">
              {storeName} no tiene nada con existencias para «{text}».
            </p>
          )}
          <ul className="results">
            {products.map((p) => (
              <li key={p.productId} className="card">
                <Thumb src={p.imageUrl} alt={p.name} />
                <div className="info">
                  <strong>{p.name}</strong>
                  <span className="meta">{formatPrice(p.price)}</span>
                </div>
                <button className="add" onClick={() => onPick({ productId: p.productId, name: p.name, qty })}>
                  Usar este
                </button>
              </li>
            ))}
          </ul>
          {!loading && result.hasMore && (
            <button className="secondary more" onClick={loadMore} disabled={loadingMore}>
              {loadingMore ? "Cargando..." : "Ver más resultados"}
            </button>
          )}
        </div>
        <div className="dialog-actions">
          {current && (
            <button className="clear" onClick={onRemove}>
              Quitar el reemplazo
            </button>
          )}
          <button className="secondary" onClick={onClose}>
            Cancelar
          </button>
        </div>
      </div>
    </div>
  );
}
