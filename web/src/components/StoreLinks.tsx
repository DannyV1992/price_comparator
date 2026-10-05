"use client";

import { LinksPopup, type LinkEntry } from "./LinksPopup";

export type { LinkEntry };
export type SortDir = "asc" | "desc" | null;

type Props = { storeName: string; entries: LinkEntry[]; sort: SortDir; onSort: () => void };

// Encabezado del supermercado: el nombre muestra los enlaces a los productos; la flecha ordena la tabla por su precio.
export function StoreLinks({ storeName, entries, sort, onSort }: Props) {
  return (
    <>
      <LinksPopup title={storeName} entries={entries} className="store-head" hint="Ver los enlaces de los productos">
        {storeName}
      </LinksPopup>
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
    </>
  );
}
