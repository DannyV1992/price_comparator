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
  onPick: (sub: Substitute) => void;
  onRemove: () => void;
  onClose: () => void;
};

// Las dos primeras palabras del nombre (p. ej. «Arroz precocido»): un buen punto de partida para buscar algo parecido.
const firstWords = (name: string) => (name.match(/\p{L}+/gu) ?? []).slice(0, 2).join(" ");

export function SubstituteDialog({ itemName, excludeProductId, storeId, storeName, current, onPick, onRemove, onClose }: Props) {
  const [query, setQuery] = useState(() => firstWords(itemName));
  const [result, setResult] = useState<{ q: string; products: StoreHit[] }>({ q: "", products: [] });
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
        const res = await fetch(`/api/search?q=${encodeURIComponent(text)}&store=${storeId}`, { signal: controller.signal });
        const data = (await res.json()) as { products: StoreHit[] };
        setResult({ q: text, products: data.products });
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

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" role="dialog" aria-modal="true" aria-label={`Reemplazar en ${storeName}`} onClick={(e) => e.stopPropagation()}>
        <h3>Reemplazar en {storeName}</h3>
        <p className="meta">
          «{itemName}» no está disponible en {storeName}. Elige un producto parecido que esta tienda sí tenga; en la tabla
          quedará marcado como reemplazo.
        </p>
        {current && (
          <p className="meta">
            Reemplazo actual: <b>{current.name}</b>
          </p>
        )}
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
          {!loading && text && products.length === 0 && <p className="hint">{storeName} no tiene nada con existencias para «{text}».</p>}
          <ul className="results">
            {products.map((p) => (
              <li key={p.productId} className="card">
                <Thumb src={p.imageUrl} alt={p.name} />
                <div className="info">
                  <strong>{p.name}</strong>
                  <span className="meta">{formatPrice(p.price)}</span>
                </div>
                <button className="add" onClick={() => onPick({ productId: p.productId, name: p.name })}>
                  Usar este
                </button>
              </li>
            ))}
          </ul>
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
