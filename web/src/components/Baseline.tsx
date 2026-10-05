"use client";

import { formatPrice } from "@/lib/format";
import type { Row, StoreTotal } from "@/lib/compute";
import { updateSettings, useSettings } from "@/lib/settings";
import { pair, percent } from "./Versus";

// Un supermercado elegido contra todos los demás, en pesos y en porcentaje.
export function Baseline({ rows, stores, onlyCommon }: { rows: Row[]; stores: StoreTotal[]; onlyCommon: boolean }) {
  const { baseId } = useSettings();
  if (stores.length < 2 || rows.length === 0) return null;

  // Si la tienda elegida ya no está entre las elegidas arriba, se usa la primera.
  const base = stores.find((s) => s.storeId === baseId) ?? stores[0];
  const others = stores.filter((s) => s.storeId !== base.storeId);
  const results = others.map((o) => ({ store: o, ...pair(rows, base.storeId, o.storeId) }));
  const cheaper = results.filter((r) => r.count > 0 && r.totalA < r.totalB).length;
  const pricier = results.filter((r) => r.count > 0 && r.totalA > r.totalB).length;

  return (
    <section className="compare">
      <h2>Comparativa de un supermercado vs otros</h2>
      <label className="base-pick">
        Comparar
        <select value={base.storeId} onChange={(e) => updateSettings({ baseId: Number(e.target.value) })}>
          {stores.map((s) => (
            <option key={s.storeId} value={s.storeId}>
              {s.storeName}
            </option>
          ))}
        </select>
        contra los demás supermercados
      </label>
      <p className="vs-summary">
        <b>{base.storeName}</b> es más barato que {cheaper} y más caro que {pricier} de {others.length}.
      </p>
      <div className="table-wrap">
        <table className="compact">
          <thead>
            <tr>
              <th>Competencia</th>
              <th>{base.storeName} vs competencia</th>
              <th>Diferencia</th>
              <th>Productos</th>
            </tr>
          </thead>
          <tbody>
            {results.map(({ store, totalA, totalB, count }) => {
              if (count === 0) {
                return (
                  <tr key={store.storeId}>
                    <th scope="row">{store.storeName}</th>
                    <td className="none" colSpan={3}>
                      sin productos en común
                    </td>
                  </tr>
                );
              }
              const diff = totalA - totalB;
              const cls = diff < 0 ? "cheaper" : diff > 0 ? "pricier" : undefined;
              const sign = diff < 0 ? "−" : diff > 0 ? "+" : "";
              return (
                <tr key={store.storeId}>
                  <th scope="row">{store.storeName}</th>
                  <td>
                    {formatPrice(totalA)} <span className="times">vs</span> {formatPrice(totalB)}
                  </td>
                  <td className={cls}>
                    <b>
                      {sign}
                      {formatPrice(Math.abs(diff))}
                    </b>{" "}
                    ({sign}
                    {percent.format(Math.abs(diff) / totalB)})
                  </td>
                  <td>{count}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="meta">
        {onlyCommon
          ? "Se suman solo los productos que tienen todos los supermercados elegidos."
          : `Con cada competidor se suman solo los productos que tiene junto con ${base.storeName}.`}{" "}
        Verde: {base.storeName} es más barato. Rojo: es más caro.
      </p>
    </section>
  );
}
