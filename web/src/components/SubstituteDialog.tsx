"use client";

import { useEffect, useState } from "react";
import type { Substitute } from "@/lib/list";
import { formatPrice } from "@/lib/format";
import { equivalentQty, formatQty, formatSize, parseSize } from "@/lib/size";
import { PRICESMART_ID } from "@/lib/stores";
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
  const [qtyText, setQtyText] = useState(formatQty(current?.qty ?? 1)); // cuántos del reemplazo por cada unidad del original
  const qty = Number(qtyText.replace(",", "."));
  const validQty = Number.isFinite(qty) && qty > 0;
  const club = storeId === PRICESMART_ID; // solo PriceSmart: equivalencia por tamaño y cantidades fraccionarias
  const ownSize = club ? parseSize(itemName) : null;
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
            {(current.qty ?? 1) !== 1 && <> ×{formatQty(current.qty ?? 1)}</>}
            {validQty && qty !== (current.qty ?? 1) && (
              <>
                {" "}
                <button className="clear" onClick={() => onPick({ ...current, qty })}>
                  Guardar la cantidad
                </button>
              </>
            )}
          </p>
        )}
        {club ? (
          <>
            <label className="qty-pick">
              Cantidad del reemplazo que necesitas en lugar de «{itemName}»
              <input
                className="qty-input"
                inputMode="decimal"
                value={qtyText}
                onChange={(e) => setQtyText(e.target.value)}
                aria-invalid={!validQty}
              />
            </label>
            <p className="meta">
              {ownSize
                ? `Tu producto es de ${formatSize(ownSize)}. Cada resultado te ofrece el equivalente a ese tamaño o el paquete entero; la cantidad de arriba se usa cuando no se puede calcular el equivalente (1 es un paquete, 0,5 es medio).`
                : "No pude leer el tamaño de tu producto, así que escribe la cantidad arriba: 1 es un paquete, 0,5 es medio paquete, 2 son dos paquetes."}
            </p>
          </>
        ) : (
          <label className="qty-pick">
            Unidades del reemplazo por cada «{itemName}»
            <span className="qty">
              <button aria-label="Quitar uno" onClick={() => setQtyText(String(Math.max(1, Math.round(qty) - 1)))}>
                −
              </button>
              <span>{validQty ? qty : 1}</span>
              <button aria-label="Agregar uno" onClick={() => setQtyText(String(Math.max(1, Math.round(qty)) + 1))}>
                +
              </button>
            </span>
          </label>
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
          {!loading && text && products.length === 0 && (
            <p className="hint">
              {storeName} no tiene nada con existencias para «{text}».
            </p>
          )}
          <ul className="results">
            {products.map((p) => {
              const parsed = club ? (parseSize(p.storeProductName) ?? parseSize(p.name)) : null;
              const eq = equivalentQty(ownSize, parsed);
              const hasEq = eq != null && eq > 0 && eq !== 1;
              return (
                <li key={p.productId} className="card">
                  <Thumb src={p.imageUrl} alt={p.name} />
                  <div className="info">
                    <strong>{p.name}</strong>
                    <span className="meta">
                      {formatPrice(p.price)}
                      {parsed && <> · {formatSize(parsed)}</>}
                    </span>
                    {hasEq && (
                      <span className="meta">
                        Equivale a «{itemName}» de tu lista por <b>{formatPrice(p.price * eq)}</b> ({formatQty(eq)} de
                        este paquete)
                      </span>
                    )}
                  </div>
                  <div className="pick-actions">
                    {hasEq && (
                      <button className="add" onClick={() => onPick({ productId: p.productId, name: p.name, qty: eq })}>
                        Usar equivalente
                      </button>
                    )}
                    {hasEq ? (
                      <button
                        className="secondary"
                        onClick={() => onPick({ productId: p.productId, name: p.name, qty: 1 })}
                      >
                        Usar el paquete entero
                      </button>
                    ) : (
                      <button
                        className="add"
                        disabled={!validQty}
                        onClick={() => onPick({ productId: p.productId, name: p.name, qty })}
                      >
                        Usar este
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
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
