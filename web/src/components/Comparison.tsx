"use client";

import { useEffect, useState } from "react";
import { setSubstitute, useList } from "@/lib/list";
import { buildComparison, type Offer } from "@/lib/compute";
import { formatPrice } from "@/lib/format";
import type { Store } from "@/lib/search";
import { StoreChips } from "./StoreChips";
import { SubstituteDialog } from "./SubstituteDialog";

type Picker = { productId: string; storeId: number };

export function Comparison() {
  const list = useList();
  // Se piden los precios de los productos de la lista y de sus reemplazos.
  const ids = new Set(list.flatMap((i) => [i.productId, ...Object.values(i.subs ?? {}).map((s) => s.productId)]));
  const key = [...ids].sort().join("|");
  const [loaded, setLoaded] = useState<{ key: string; offers: Offer[] }>({ key: "", offers: [] });
  const [picker, setPicker] = useState<Picker | null>(null);
  const [hidden, setHidden] = useState<number[]>([]); // tiendas que no quiero ver en la comparación
  const [storeList, setStoreList] = useState<Store[]>([]);

  // Todas las tiendas salen como columna, aunque no tengan nada de la lista: así se puede elegir un reemplazo en ellas.
  useEffect(() => {
    fetch("/api/stores")
      .then((res) => res.json() as Promise<{ stores: Store[] }>)
      .then((data) => setStoreList(data.stores))
      .catch(() => {}); // sin la lista, solo salen las tiendas que tienen precios de la lista
  }, []);

  useEffect(() => {
    if (!key) return;
    const controller = new AbortController();
    (async () => {
      try {
        const res = await fetch("/api/compare", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ids: key.split("|") }),
          signal: controller.signal,
        });
        const data = (await res.json()) as { offers: Offer[] };
        setLoaded({ key, offers: data.offers });
      } catch {
        // cancelada porque la lista cambió
      }
    })();
    return () => controller.abort();
  }, [key]);

  if (list.length === 0) return null;
  if (loaded.key !== key) {
    return (
      <section className="compare">
        <p className="hint">Buscando precios...</p>
      </section>
    );
  }

  // Las tiendas ocultas no cuentan para nada: ni columnas, ni totales, ni «la más barata».
  const allStores = [
    ...new Map([
      ...storeList.map((s) => [s.id, s] as const),
      ...loaded.offers.map((o) => [o.storeId, { id: o.storeId, name: o.storeName }] as const),
    ]).values(),
  ].sort((a, b) => a.name.localeCompare(b.name));
  const toggleStore = (id: number) => setHidden((cur) => (cur.includes(id) ? cur.filter((s) => s !== id) : [...cur, id]));
  const { rows, stores, bestComplete, split } = buildComparison(
    list,
    loaded.offers.filter((o) => !hidden.includes(o.storeId)),
    allStores.filter((s) => !hidden.includes(s.id)),
  );
  const top = stores[0];
  const saving = bestComplete ? bestComplete.total - split.total : 0;
  const storeName = (id: number) => stores.find((s) => s.storeId === id)?.storeName ?? "";

  const pickerItem = picker && list.find((i) => i.productId === picker.productId);
  const notes = rows.flatMap((row) =>
    stores.flatMap((s) => {
      const sub = row.cells.get(s.storeId);
      return sub && "substitute" in sub && sub.substitute
        ? [{ key: `${row.item.productId}|${s.storeId}`, store: s.storeName, item: row.item.name, sub: sub.substitute.name, out: sub.status === "out" }]
        : [];
    }),
  );

  return (
    <section className="compare">
      <h2>Comparación</h2>

      {allStores.length > 1 && (
        <StoreChips
          label="Tiendas en la comparación:"
          stores={allStores}
          isOn={(id) => !hidden.includes(id)}
          onToggle={toggleStore}
          onAll={{ label: "Todas", active: hidden.length === 0, run: () => setHidden([]) }}
        />
      )}

      <div className="summary">
        {bestComplete ? (
          <p>
            <b>{bestComplete.storeName}</b> tiene todos tus productos
            {bestComplete.substituted > 0 && (
              <> (con {bestComplete.substituted} reemplazo{bestComplete.substituted > 1 ? "s" : ""})</>
            )}{" "}
            y es la más barata para comprar todo en un solo lugar: <b>{formatPrice(bestComplete.total)}</b>.
          </p>
        ) : top ? (
          <p>
            Ninguna tienda tiene todos tus productos. La que más tiene es <b>{top.storeName}</b>: {top.covered} de{" "}
            {rows.length} por <b>{formatPrice(top.total)}</b>.
          </p>
        ) : (
          <p>{hidden.length > 0 ? "Elige al menos una tienda para comparar." : "Ninguna tienda tiene estos productos ahora."}</p>
        )}
        {split.total > 0 && (
          <p>
            Comprando cada producto donde es más barato pagarías <b>{formatPrice(split.total)}</b>
            {saving > 0 && <> (ahorras {formatPrice(saving)} frente a {bestComplete?.storeName})</>}
            {split.missing > 0 && <>, sin contar {split.missing} que no está{split.missing > 1 ? "n" : ""} disponible{split.missing > 1 ? "s" : ""} en ninguna tienda</>}.
          </p>
        )}
      </div>

      {stores.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Producto</th>
                {stores.map((s) => (
                  <th key={s.storeId}>{s.storeName}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.item.productId}>
                  <th scope="row">
                    {row.item.name}
                    {row.item.qty > 1 && <span className="times"> ×{row.item.qty}</span>}
                    {row.outlier && <em className="warn"> · precios muy distintos, revisa</em>}
                  </th>
                  {stores.map((s) => {
                    const cell = row.cells.get(s.storeId)!;
                    const open = () => setPicker({ productId: row.item.productId, storeId: s.storeId });

                    if (cell.status === "none") {
                      return (
                        <td key={s.storeId} className="none">
                          <button className="cell-btn" onClick={open} title="Esta tienda no lo vende. Clic para elegir un reemplazo">
                            —
                          </button>
                        </td>
                      );
                    }
                    if (cell.status === "out") {
                      return (
                        <td key={s.storeId} className={cell.substitute ? "none replaced-out" : "none"}>
                          <button className="cell-btn" onClick={open}>
                            {cell.substitute ? "Reemplazo agotado" : "Agotado"}
                            <small>{cell.substitute ? "cambiar" : "reemplazar"}</small>
                          </button>
                        </td>
                      );
                    }
                    const { offer, substitute } = cell;
                    const price = offer.url ? (
                      <a href={offer.url} target="_blank" rel="noreferrer" title={offer.storeProductName ?? undefined}>
                        {formatPrice(offer.price)}
                      </a>
                    ) : (
                      formatPrice(offer.price)
                    );
                    if (substitute) {
                      return (
                        <td
                          key={s.storeId}
                          className="replaced"
                          title={`Reemplazo: «${substitute.name}». El producto elegido no está disponible en ${s.storeName}.`}
                        >
                          {price}
                          <button className="cell-btn note" onClick={open}>
                            ↻ {substitute.name}
                          </button>
                        </td>
                      );
                    }
                    return (
                      <td key={s.storeId} className={offer.price === row.minPrice ? "best" : undefined}>
                        {price}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <th scope="row">Total</th>
                {stores.map((s) => (
                  <td key={s.storeId} className={s.covered < rows.length ? "partial" : undefined}>
                    <b>{formatPrice(s.total)}</b>
                    {s.covered < rows.length && (
                      <span className="meta">
                        {s.covered} de {rows.length}
                      </span>
                    )}
                    {s.substituted > 0 && (
                      <span className="meta replaced-count">
                        {s.substituted} reemplazo{s.substituted > 1 ? "s" : ""}
                      </span>
                    )}
                  </td>
                ))}
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {notes.length > 0 && (
        <ul className="notes">
          {notes.map((n) => (
            <li key={n.key}>
              En <b>{n.store}</b>, «{n.item}» se reemplazó por «{n.sub}»{n.out && " (también está agotado)"}.
            </li>
          ))}
        </ul>
      )}

      <p className="hint">
        El verde es el precio más bajo de cada producto. El naranja es un reemplazo: otro producto, elegido por ti porque
        el original no está en esa tienda; cuenta en el total de la tienda pero no en «lo más barato de cada producto».
        Los totales suman solo lo que la tienda tiene disponible; si le faltan productos, no es comparable con una tienda
        completa. Haz clic en «Agotado» o en «—» para elegir un reemplazo.
      </p>

      {picker && pickerItem && (
        <SubstituteDialog
          itemName={pickerItem.name}
          excludeProductId={pickerItem.productId}
          storeId={picker.storeId}
          storeName={storeName(picker.storeId)}
          current={pickerItem.subs?.[String(picker.storeId)]}
          onPick={(sub) => {
            setSubstitute(pickerItem.productId, picker.storeId, sub);
            setPicker(null);
          }}
          onRemove={() => {
            setSubstitute(pickerItem.productId, picker.storeId, null);
            setPicker(null);
          }}
          onClose={() => setPicker(null)}
        />
      )}
    </section>
  );
}
