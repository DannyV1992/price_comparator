"use client";

import { useEffect, useRef, useState } from "react";

export type LinkEntry = {
  key: string;
  label: string; // nombre del producto en la tienda
  price?: string; // sin precio: no está disponible
  url?: string | null;
  note?: string;
};

export type SortDir = "asc" | "desc" | null;

type Props = { storeName: string; entries: LinkEntry[]; sort: SortDir; onSort: () => void };

// Encabezado de la tienda: el nombre muestra los enlaces a los productos; la flecha ordena la tabla por su precio.
export function StoreLinks({ storeName, entries, sort, onSort }: Props) {
  const btn = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  // La tabla tiene desplazamiento propio y recortaría el menú: por eso se coloca con position: fixed.
  const open = () => {
    if (pos) return setPos(null);
    const r = btn.current!.getBoundingClientRect();
    setPos({ top: r.bottom + 4, left: Math.max(8, Math.min(r.left, window.innerWidth - 348)) });
  };

  useEffect(() => {
    if (!pos) return;
    const close = () => setPos(null);
    const outside = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!menu.current?.contains(t) && !btn.current?.contains(t)) close();
    };
    const escape = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", escape);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", escape);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [pos]);

  return (
    <>
      <button
        ref={btn}
        className="store-head"
        aria-haspopup="true"
        aria-expanded={!!pos}
        onClick={open}
        title="Ver los enlaces de los productos"
      >
        {storeName}
      </button>
      <button
        className={sort ? "sort-btn on" : "sort-btn"}
        onClick={onSort}
        aria-label={`Ordenar por precio en ${storeName}`}
        title={
          sort === "asc"
            ? "Del más barato al más caro (clic: al revés)"
            : sort === "desc"
              ? "Del más caro al más barato (clic: quitar orden)"
              : "Ordenar por precio en este supermercado"
        }
      >
        {sort === "asc" ? "▲" : sort === "desc" ? "▼" : "⇅"}
      </button>
      {pos && (
        <div ref={menu} className="links-menu" style={{ top: pos.top, left: pos.left }}>
          <strong>{storeName}</strong>
          <ul>
            {entries.map((e) => (
              <li key={e.key} className={e.price ? undefined : "off"}>
                {e.url && e.price ? (
                  <a href={e.url} target="_blank" rel="noreferrer">
                    {e.label}
                  </a>
                ) : (
                  <span>{e.label}</span>
                )}
                <span className="links-price">{e.price ?? e.note}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
