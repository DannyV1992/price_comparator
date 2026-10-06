"use client";

import { useEffect, useState } from "react";
import { setSubstitute, useList } from "@/lib/list";
import { updateSettings, useSettings } from "@/lib/settings";
import { buildComparison, cellPrice, isUsable, type Offer } from "@/lib/compute";
import { formatPrice } from "@/lib/format";
import { formatQty } from "@/lib/size";
import { PRICESMART_ID } from "@/lib/stores";
import type { Store } from "@/lib/search";
import { StoreChips } from "./StoreChips";
import { LinksPopup } from "./LinksPopup";
import { StoreLinks, type LinkEntry } from "./StoreLinks";
import { SubstituteDialog } from "./SubstituteDialog";
import { Baseline } from "./Baseline";
import { Versus } from "./Versus";

type Picker = { productId: string; storeId: number };

const REAL_TOTAL_HINT =
  "PriceSmart solo vende paquetes completos. El total de arriba suma la parte equivalente a tu lista; este es lo que costarían los paquetes enteros que tendrías que llevar.";

export function Comparison() {
  const list = useList();
  // Se piden los precios de los productos de la lista y de sus reemplazos.
  const ids = new Set(list.flatMap((i) => [i.productId, ...Object.values(i.subs ?? {}).map((s) => s.productId)]));
  const key = [...ids].sort().join("|");
  const [loaded, setLoaded] = useState<{ key: string; offers: Offer[] }>({
    key: "",
    offers: [],
  });
  // Supermercados ocultos, qué suma el total y el orden de la tabla: se guardan en el navegador junto con la lista.
  const { hidden, totalMode, sort } = useSettings();
  const [picker, setPicker] = useState<Picker | null>(null);
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
  const toggleStore = (id: number) =>
    updateSettings({ hidden: hidden.includes(id) ? hidden.filter((s) => s !== id) : [...hidden, id] });
  const shownOffers = loaded.offers.filter((o) => !hidden.includes(o.storeId));
  const shownStores = allStores.filter((s) => !hidden.includes(s.id));
  const full = buildComparison(list, shownOffers, shownStores);
  // «En común»: todas las tiendas elegidas tienen un precio disponible (del producto o de su reemplazo).
  const common = full.rows.filter(
    (r) => full.stores.length > 0 && full.stores.every((s) => r.cells.get(s.storeId)?.status === "price"),
  );
  const { rows: listed, stores, bestComplete, split } = full;
  // Total de solo lo que tienen todas las tiendas elegidas; se puede ver en la última línea de la tabla.
  const commonTotals = new Map(
    stores.map((s) => [
      s.storeId,
      common.reduce((sum, r) => {
        const cell = r.cells.get(s.storeId);
        return cell?.status === "price" ? sum + cellPrice(cell) * r.item.qty : sum;
      }, 0),
    ]),
  );
  const commonMode = totalMode === "common" && stores.length > 1;
  // PriceSmart solo vende paquetes enteros: lo que se pagaría de verdad redondea hacia arriba cuántos paquetes se llevan.
  const packsTotal = (storeId: number, from: typeof listed) =>
    from.reduce((sum, r) => {
      const cell = r.cells.get(storeId);
      if (cell?.status !== "price") return sum;
      const packs = Math.ceil(Math.round((cell.substitute?.qty ?? 1) * r.item.qty * 10000) / 10000);
      return sum + cell.offer.price * packs;
    }, 0);
  const realTotal = (storeId: number) => {
    if (storeId !== PRICESMART_ID) return null;
    const real = packsTotal(storeId, commonMode ? common : listed);
    const shown = commonMode ? commonTotals.get(storeId) : stores.find((s) => s.storeId === storeId)?.total;
    return shown != null && Math.round(real) !== Math.round(shown) ? real : null;
  };
  const minCommon = Math.min(...commonTotals.values());
  const top = stores[0];
  // Con un orden activo, los productos sin precio en esa tienda quedan al final.
  const sortStore = sort && stores.some((s) => s.storeId === sort.storeId) ? sort : null;
  const priceIn = (row: (typeof listed)[number]) => {
    const cell = row.cells.get(sortStore!.storeId);
    return cell?.status === "price" ? cellPrice(cell) : null;
  };
  const sorted = sortStore
    ? [...listed].sort((a, b) => {
        const [pa, pb] = [priceIn(a), priceIn(b)];
        if (pa == null || pb == null) return pa == null ? (pb == null ? 0 : 1) : -1;
        return sortStore.dir === "asc" ? pa - pb : pb - pa;
      })
    : listed;
  // Con «solo lo que tienen todas», se esconden las filas que no se están sumando.
  const rows = commonMode ? sorted.filter((r) => common.includes(r)) : sorted;
  // Un clic en la flecha: de menor a mayor, luego de mayor a menor, luego sin orden.
  const cycleSort = (storeId: number) =>
    updateSettings({
      sort: sort?.storeId !== storeId ? { storeId, dir: "asc" } : sort.dir === "asc" ? { storeId, dir: "desc" } : null,
    });
  const saving = bestComplete ? bestComplete.total - split.total : 0;
  const storeName = (id: number) => stores.find((s) => s.storeId === id)?.storeName ?? "";

  // Verde: el precio más bajo del producto; rojo: el más alto (los reemplazos también cuentan).
  const priceClass = (row: (typeof rows)[number], price: number) =>
    price === row.minPrice ? "best" : price === row.maxPrice ? "worst" : undefined;

  // «Nombre» o «Nombre» ×2, para los textos sobre un reemplazo.
  const subText = (sub: { name: string; qty?: number }) =>
    `«${sub.name}»${(sub.qty ?? 1) !== 1 ? ` ×${formatQty(sub.qty ?? 1)}` : ""}`;

  // Enlaces a los productos de la comparación en una tienda (los reemplazos apuntan al producto que los reemplaza).
  const linksFor = (storeId: number): LinkEntry[] =>
    rows.map((row) => {
      const cell = row.cells.get(storeId)!;
      const key = row.item.productId;
      if (cell.status === "price") {
        return {
          key,
          label: cell.offer.storeProductName ?? row.item.name,
          price: formatPrice(cellPrice(cell)),
          url: cell.offer.url,
        };
      }
      return {
        key,
        label: row.item.name,
        note: cell.status === "out" ? "Agotado" : "No lo vende",
      };
    });

  // Enlaces de un producto en cada supermercado (los reemplazos apuntan al producto que los reemplaza).
  const linksForRow = (row: (typeof rows)[number]): LinkEntry[] =>
    stores.map((s) => {
      const cell = row.cells.get(s.storeId)!;
      if (cell.status === "price") {
        return {
          key: String(s.storeId),
          label: s.storeName,
          detail: cell.offer.storeProductName ?? row.item.name,
          price: formatPrice(cellPrice(cell)),
          url: cell.offer.url,
        };
      }
      return {
        key: String(s.storeId),
        label: s.storeName,
        note: cell.status === "out" ? "Agotado" : "No lo vende",
      };
    });

  const pickerItem = picker && list.find((i) => i.productId === picker.productId);
  const notes = rows.flatMap((row) =>
    stores.flatMap((s) => {
      const sub = row.cells.get(s.storeId);
      return sub && "substitute" in sub && sub.substitute
        ? [
            {
              key: `${row.item.productId}|${s.storeId}`,
              store: s.storeName,
              item: row.item.name,
              sub: subText(sub.substitute),
              out: sub.status === "out",
            },
          ]
        : [];
    }),
  );

  return (
    <>
      <section className="compare">
        <h2>Comparación</h2>

        {allStores.length > 1 && (
          <StoreChips
            label="Supermercados en la comparación:"
            stores={allStores}
            isOn={(id) => !hidden.includes(id)}
            onToggle={toggleStore}
            onAll={{
              label: "Todos",
              active: hidden.length === 0,
              run: () => updateSettings({ hidden: [] }),
            }}
          />
        )}

        <div className="summary">
          {bestComplete ? (
            <p>
              <b>{bestComplete.storeName}</b> tiene todos tus productos
              {bestComplete.substituted > 0 && (
                <>
                  {" "}
                  (con {bestComplete.substituted} reemplazo
                  {bestComplete.substituted > 1 ? "s" : ""})
                </>
              )}{" "}
              y es el más barato para comprar todo en un solo lugar: <b>{formatPrice(bestComplete.total)}</b>.
            </p>
          ) : top ? (
            <p>
              Ningún supermercado tiene todos tus productos. El que más tiene es <b>{top.storeName}</b>: {top.covered}{" "}
              de {rows.length} por <b>{formatPrice(top.total)}</b>.
            </p>
          ) : (
            <p>
              {hidden.length > 0
                ? "Elige al menos un supermercado para comparar."
                : "Ningún supermercado tiene estos productos ahora."}
            </p>
          )}
          {split.total > 0 && (
            <p>
              Comprando cada producto donde es más barato pagarías <b>{formatPrice(split.total)}</b>
              {saving > 0 && (
                <>
                  {" "}
                  (ahorras {formatPrice(saving)} frente a {bestComplete?.storeName})
                </>
              )}
              {split.missing > 0 && (
                <>
                  , sin contar {split.missing} que no está
                  {split.missing > 1 ? "n" : ""} disponible
                  {split.missing > 1 ? "s" : ""} en ningún supermercado
                </>
              )}
              .
            </p>
          )}
        </div>

        {stores.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="num">#</th>
                  <th>Producto</th>
                  {stores.map((s) => (
                    <th key={s.storeId}>
                      <StoreLinks
                        storeName={s.storeName}
                        entries={linksFor(s.storeId)}
                        sort={sortStore?.storeId === s.storeId ? sortStore.dir : null}
                        onSort={() => cycleSort(s.storeId)}
                      />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={row.item.productId}>
                    <td className="num">{index + 1}</td>
                    <th scope="row">
                      <LinksPopup
                        title={row.item.name}
                        entries={linksForRow(row)}
                        className="store-head item-head"
                        hint="Ver los enlaces de este producto en cada supermercado"
                      >
                        {row.item.name}
                      </LinksPopup>
                      {row.item.qty > 1 && <span className="times"> (×{row.item.qty})</span>}
                      {row.outlier && <em className="warn"> · precios muy distintos, revisa</em>}
                    </th>
                    {stores.map((s) => {
                      const cell = row.cells.get(s.storeId)!;
                      const open = () =>
                        setPicker({
                          productId: row.item.productId,
                          storeId: s.storeId,
                        });

                      if (cell.status === "none") {
                        return (
                          <td key={s.storeId} className="none">
                            <button
                              className="cell-btn"
                              onClick={open}
                              title="Este supermercado no lo vende. Clic para elegir un reemplazo"
                            >
                              —
                            </button>
                          </td>
                        );
                      }
                      if (cell.status === "out") {
                        return (
                          <td key={s.storeId} className="none">
                            <button
                              className="cell-btn"
                              onClick={open}
                              title={
                                cell.substitute ? `Reemplazado por ${subText(cell.substitute)} (agotado)` : undefined
                              }
                            >
                              {cell.substitute ? "Reemplazo agotado" : "Agotado"}
                              <small>{cell.substitute ? "Cambiar" : "Reemplazar"}</small>
                            </button>
                          </td>
                        );
                      }
                      const { offer, substitute } = cell;
                      const shown = cellPrice(cell);
                      // Con varias unidades, la celda muestra el precio por la cantidad (lo que suma el total) y, debajo, el de una.
                      const lineTotal = shown * row.item.qty;
                      const unitNote = row.item.qty > 1 && <span className="meta">{formatPrice(shown)} c/u</span>;
                      const price = offer.url ? (
                        <a
                          href={offer.url}
                          target="_blank"
                          rel="noreferrer"
                          title={offer.storeProductName ?? undefined}
                        >
                          {formatPrice(lineTotal)}
                        </a>
                      ) : (
                        formatPrice(lineTotal)
                      );
                      if (substitute) {
                        // Con otra cantidad (p. ej. un paquete grande), se compara el precio equivalente con el más barato de los demás.
                        const qty = substitute.qty ?? 1;
                        const club = s.storeId === PRICESMART_ID; // el detalle del paquete es solo para PriceSmart
                        const packNote =
                          club && qty !== 1
                            ? ` Se vende a ${formatPrice(offer.price)}; el precio de la celda es la parte equivalente a tu producto (×${formatQty(qty)}), no lo que pagarías por el paquete.`
                            : "";
                        return (
                          <td key={s.storeId} className={`replaced ${priceClass(row, shown) ?? ""}`}>
                            {price}
                            {unitNote}
                            <span className="cell-tip" data-tip={`Reemplazado por ${subText(substitute)}.${packNote}`}>
                              <button className="cell-btn note" onClick={open}>
                                ↻ Reemplazado{qty !== 1 && ` ×${formatQty(qty)}`}
                              </button>
                            </span>
                            {club && qty !== 1 && <span className="meta">Se vende a {formatPrice(offer.price)}</span>}
                          </td>
                        );
                      }
                      return (
                        <td key={s.storeId} className={priceClass(row, shown)}>
                          {price}
                          {unitNote}
                          <button
                            className="cell-btn swap"
                            onClick={open}
                            title={`Reemplazar este producto en ${s.storeName}`}
                          >
                            ↻ Reemplazar
                          </button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <th scope="row" colSpan={2}>
                    {stores.length > 1 ? (
                      <select
                        className="total-mode"
                        value={totalMode}
                        onChange={(e) => updateSettings({ totalMode: e.target.value as "all" | "common" })}
                        aria-label="Qué suma el total"
                      >
                        <option value="all">Total de lo que está disponible en cada supermercado</option>
                        <option value="common">Total solo de lo que está disponible en todos los supermercados</option>
                      </select>
                    ) : (
                      "Total"
                    )}
                    {commonMode && common.length === 0 && (
                      <span className="meta">Ningún producto está en todos los supermercados.</span>
                    )}
                  </th>
                  {stores.map((s) =>
                    commonMode ? (
                      <td
                        key={s.storeId}
                        className={common.length > 0 && commonTotals.get(s.storeId) === minCommon ? "best" : undefined}
                      >
                        <b>{common.length > 0 ? formatPrice(commonTotals.get(s.storeId) ?? 0) : "—"}</b>
                        {common.length > 0 && realTotal(s.storeId) != null && (
                          <span className="meta real-total" tabIndex={0} data-tip={REAL_TOTAL_HINT}>
                            Pagarías realmente {formatPrice(realTotal(s.storeId)!)} ⓘ
                          </span>
                        )}
                      </td>
                    ) : (
                      <td key={s.storeId} className={s.covered < rows.length ? "partial" : undefined}>
                        <b>{formatPrice(s.total)}</b>
                        {s.covered < rows.length && (
                          <span className="meta">
                            {s.covered} de {rows.length}
                          </span>
                        )}
                        {s.substituted > 0 && (
                          <span className="meta replaced-count">
                            {s.substituted} reemplazo
                            {s.substituted > 1 ? "s" : ""}
                          </span>
                        )}
                        {realTotal(s.storeId) != null && (
                          <span className="meta real-total" tabIndex={0} data-tip={REAL_TOTAL_HINT}>
                            Pagarías realmente {formatPrice(realTotal(s.storeId)!)} ⓘ
                          </span>
                        )}
                      </td>
                    ),
                  )}
                </tr>
              </tfoot>
            </table>
          </div>
        )}

        {notes.length > 0 && (
          <ul className="notes">
            {notes.map((n) => (
              <li key={n.key}>
                En <b>{n.store}</b>, «{n.item}» se reemplazó por {n.sub}
                {n.out && " (también está agotado)"}.
              </li>
            ))}
          </ul>
        )}

        <p className="hint">
          El verde es el precio más bajo de cada producto y el rojo el más alto. Un reemplazo se marca con «↻
          Reemplazado»: es otro producto, elegido por ti para ese supermercado; cuenta en los colores y en los totales,
          con su cantidad. Los totales suman solo lo que el supermercado tiene disponible; si le faltan productos, no es
          comparable con un supermercado completo. Haz clic en «Agotado» o en «—» para elegir un reemplazo, o en «↻
          Reemplazar» (al pasar el mouse por un precio) para cambiar un producto que sí está disponible.
        </p>

        {picker && pickerItem && (
          <SubstituteDialog
            itemName={pickerItem.name}
            excludeProductId={pickerItem.productId}
            storeId={picker.storeId}
            storeName={storeName(picker.storeId)}
            current={pickerItem.subs?.[String(picker.storeId)]}
            available={isUsable(
              loaded.offers.find((o) => o.productId === pickerItem.productId && o.storeId === picker.storeId),
            )}
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
      <Versus rows={commonMode ? common : full.rows} stores={stores} onlyCommon={commonMode} />
      <Baseline rows={commonMode ? common : full.rows} stores={stores} onlyCommon={commonMode} />
    </>
  );
}
