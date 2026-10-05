"use client";

import { useEffect, useRef, useState } from "react";
import type { Store } from "@/lib/search";

type Props = {
  label: string;
  stores: Store[];
  isOn: (storeId: number) => boolean;
  onToggle: (storeId: number) => void;
  onAll?: { label: string; active: boolean; run: () => void }; // opción «Todas» / «Mostrar todas»
};

// Menú desplegable con casillas para activar o desactivar tiendas.
export function StoreChips({ label, stores, isOn, onToggle, onAll }: Props) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  // Se cierra al hacer clic fuera o con Escape.
  useEffect(() => {
    if (!open) return;
    const outside = (e: MouseEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    const escape = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  const on = stores.filter((s) => isOn(s.id));
  const summary = onAll?.active
    ? "Todos"
    : on.length === 0
      ? "Ninguno"
      : on.length === 1
        ? on[0].name
        : `${on.length} de ${stores.length}`;

  return (
    <div className="chips">
      <span className="chips-label">{label}</span>
      <div className="dropdown" ref={box}>
        <button className="dropdown-btn" aria-haspopup="true" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {summary} <span aria-hidden>▾</span>
        </button>
        {open && (
          <div className="dropdown-menu" role="group" aria-label={label}>
            {onAll && (
              <label className="dropdown-item all">
                <input type="checkbox" checked={onAll.active} onChange={onAll.run} />
                {onAll.label}
              </label>
            )}
            {stores.map((s) => (
              <label key={s.id} className="dropdown-item">
                <input type="checkbox" checked={isOn(s.id)} onChange={() => onToggle(s.id)} />
                {s.name}
              </label>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
