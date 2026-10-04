"use client";

import type { Store } from "@/lib/search";

type Props = {
  label: string;
  stores: Store[];
  isOn: (storeId: number) => boolean;
  onToggle: (storeId: number) => void;
  onAll?: { label: string; active: boolean; run: () => void }; // botón «Todas» / «Mostrar todas»
};

// Botones para activar o desactivar tiendas.
export function StoreChips({ label, stores, isOn, onToggle, onAll }: Props) {
  return (
    <div className="chips" role="group" aria-label={label}>
      <span className="chips-label">{label}</span>
      {onAll && (
        <button className={onAll.active ? "chip on" : "chip"} aria-pressed={onAll.active} onClick={onAll.run}>
          {onAll.label}
        </button>
      )}
      {stores.map((s) => (
        <button key={s.id} className={isOn(s.id) ? "chip on" : "chip"} aria-pressed={isOn(s.id)} onClick={() => onToggle(s.id)}>
          {s.name}
        </button>
      ))}
    </div>
  );
}
