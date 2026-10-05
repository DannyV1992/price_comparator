import { formatPrice } from "@/lib/format";
import { cellPrice, type Row, type StoreTotal } from "@/lib/compute";

export const percent = new Intl.NumberFormat("es-CR", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

// Total de dos tiendas sumando solo los productos que las dos tienen con precio (con reemplazo o sin él).
export function pair(rows: Row[], a: number, b: number) {
  let totalA = 0;
  let totalB = 0;
  let count = 0;
  for (const row of rows) {
    const [ca, cb] = [row.cells.get(a), row.cells.get(b)];
    if (ca?.status === "price" && cb?.status === "price") {
      totalA += cellPrice(ca) * row.item.qty;
      totalB += cellPrice(cb) * row.item.qty;
      count += 1;
    }
  }
  return { totalA, totalB, count };
}

// Cuánto más barata (o cara) es cada tienda frente a cada otra, en pesos y en porcentaje.
export function Versus({ rows, stores, onlyCommon }: { rows: Row[]; stores: StoreTotal[]; onlyCommon: boolean }) {
  if (stores.length < 2 || rows.length === 0) return null;

  // Diferencia porcentual de cada casilla (negativo: la fila es más barata); se marca la más baja y la más alta.
  const pct = (a: number, b: number) => {
    const { totalA, totalB, count } = pair(rows, a, b);
    return count > 0 && totalA !== totalB ? (totalA - totalB) / totalB : null;
  };
  const all = stores.flatMap((a) => stores.map((b) => (a.storeId === b.storeId ? null : pct(a.storeId, b.storeId))));
  const values = all.filter((v): v is number => v !== null);
  const [low, high] = [Math.min(...values), Math.max(...values)];
  const marks = values.length > 1 && low !== high;

  return (
    <section className="compare">
      <h2>Matriz de comparativa entre supermercados</h2>
      <p className="meta">
        Cada casilla compara el supermercado de la fila con el de la columna, sumando{" "}
        {onlyCommon
          ? "solo los productos que tienen todos los supermercados elegidos."
          : "solo los productos que las dos tienen."}
        Verde: la fila es más barata. Rojo: la fila es más cara. 🏆 marca el porcentaje más bajo del cuadro (el mayor
        ahorro) y ⚠️ el más alto (el mayor sobreprecio).
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Supermercado</th>
              {stores.map((s) => (
                <th key={s.storeId}>vs {s.storeName}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {stores.map((a) => (
              <tr key={a.storeId}>
                <th scope="row">{a.storeName}</th>
                {stores.map((b) => {
                  if (a.storeId === b.storeId)
                    return (
                      <td key={b.storeId} className="none">
                        —
                      </td>
                    );
                  const { totalA, totalB, count } = pair(rows, a.storeId, b.storeId);
                  if (count === 0) {
                    return (
                      <td key={b.storeId} className="none">
                        sin productos en común
                      </td>
                    );
                  }
                  const diff = totalA - totalB;
                  if (diff === 0) {
                    return (
                      <td key={b.storeId}>
                        igual
                        <span className="meta">{count} productos</span>
                      </td>
                    );
                  }
                  return (
                    <td key={b.storeId} className={diff < 0 ? "cheaper" : "pricier"}>
                      {marks && diff / totalB === low && (
                        <span className="corner" title="El porcentaje más bajo: el mayor ahorro">
                          🏆
                        </span>
                      )}
                      {marks && diff / totalB === high && (
                        <span className="corner" title="El porcentaje más alto: el mayor sobreprecio">
                          ⚠️
                        </span>
                      )}
                      <b>
                        {diff < 0 ? "−" : "+"}
                        {formatPrice(Math.abs(diff))}
                      </b>
                      <span className="meta">
                        {diff < 0 ? "−" : "+"}
                        {percent.format(Math.abs(diff) / totalB)} · {count} productos
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
