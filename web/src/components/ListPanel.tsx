"use client";

import { useRef, useState } from "react";
import { downloadBackup, loadBackup } from "@/lib/backup";
import { clearList, removeItem, setQty, useList } from "@/lib/list";
import { Thumb } from "./Thumb";

export function ListPanel() {
  const list = useList();
  const [collapsed, setCollapsed] = useState(false);
  const [message, setMessage] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const units = list.reduce((sum, i) => sum + i.qty, 0);

  return (
    <aside className="panel">
      <div className="panel-head">
        <h2>
          Mi lista{" "}
          <span className="count">{list.length === 0 ? "" : `${list.length} productos · ${units} unidades`}</span>
        </h2>
        <button className="secondary panel-toggle" aria-expanded={!collapsed} onClick={() => setCollapsed((c) => !c)}>
          {collapsed ? "Mostrar" : "Minimizar"}
        </button>
      </div>
      {collapsed ? null : list.length === 0 ? (
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
                <button
                  className="remove"
                  aria-label={`Quitar ${item.name}`}
                  onClick={() => removeItem(item.productId)}
                >
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
      {!collapsed && (
        <div className="backup">
          <div className="backup-actions">
            <button className="secondary" onClick={downloadBackup} disabled={list.length === 0}>
              Guardar en un archivo
            </button>
            <button className="secondary" onClick={() => fileInput.current?.click()}>
              Cargar un archivo
            </button>
          </div>
          <input
            ref={fileInput}
            type="file"
            accept="application/json,.json"
            hidden
            onChange={async (e) => {
              const file = e.target.files?.[0];
              e.target.value = ""; // permite elegir el mismo archivo otra vez
              if (!file) return;
              if (list.length > 0 && !confirm("Cargar el archivo reemplaza tu lista actual. ¿Continuar?")) return;
              try {
                const n = await loadBackup(file);
                setMessage(`Se cargó la lista: ${n} producto${n === 1 ? "" : "s"}.`);
              } catch (err) {
                setMessage(err instanceof Error ? err.message : "No se pudo cargar el archivo.");
              }
            }}
          />
          <p className="meta">
            Tu lista, los reemplazos y cómo tienes armada la comparación se guardan solos en este navegador. El archivo
            sirve de copia o para llevarlos a otro equipo.
          </p>
          {message && <p className="meta">{message}</p>}
        </div>
      )}
    </aside>
  );
}
