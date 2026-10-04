"use client";

import { clearList, removeItem, setQty, useList } from "@/lib/list";
import { Thumb } from "./Thumb";

export function ListPanel() {
  const list = useList();
  const units = list.reduce((sum, i) => sum + i.qty, 0);

  return (
    <aside className="panel">
      <h2>
        Mi lista{" "}
        <span className="count">{list.length === 0 ? "" : `${list.length} productos · ${units} unidades`}</span>
      </h2>
      {list.length === 0 ? (
        <p className="hint">Aún no has agregado nada. Busca un producto y agrégalo.</p>
      ) : (
        <>
          <ul className="items">
            {list.map((item) => (
              <li key={item.productId} className="item">
                <Thumb src={item.imageUrl} alt={item.name} />
                <div className="info">
                  <strong>{item.name}</strong>
                  {item.brand && <span className="meta">{item.brand}</span>}
                </div>
                <div className="qty">
                  <button aria-label="Quitar uno" onClick={() => setQty(item.productId, item.qty - 1)}>
                    −
                  </button>
                  <span>{item.qty}</span>
                  <button aria-label="Agregar uno" onClick={() => setQty(item.productId, item.qty + 1)}>
                    +
                  </button>
                </div>
                <button className="remove" aria-label={`Quitar ${item.name}`} onClick={() => removeItem(item.productId)}>
                  ×
                </button>
              </li>
            ))}
          </ul>
          <button className="clear" onClick={() => confirm("¿Vaciar toda la lista?") && clearList()}>
            Vaciar lista
          </button>
        </>
      )}
    </aside>
  );
}
