"use client";

import { useSyncExternalStore } from "react";

// Cómo tengo armada la comparación. Igual que la lista, vive en el navegador (localStorage).
export type Settings = {
  hidden: number[]; // supermercados que no quiero ver en la comparación
  totalMode: "all" | "common"; // qué suma la última línea de la tabla
  sort: { storeId: number; dir: "asc" | "desc" } | null; // orden de la tabla por el precio de un supermercado
  baseId: number | null; // supermercado elegido en «un supermercado vs otros»
};

// Al abrir por primera vez empiezan ocultos Pequeño Mundo (2) y PriceSmart (6).
export const DEFAULTS: Settings = { hidden: [2, 6], totalMode: "all", sort: null, baseId: null };

const KEY = "mi-comparacion-v1";
const listeners = new Set<() => void>();
let cache: Settings | null = null;

function read(): Settings {
  if (cache) return cache;
  try {
    cache = { ...DEFAULTS, ...(JSON.parse(localStorage.getItem(KEY) ?? "{}") as Partial<Settings>) };
  } catch {
    cache = DEFAULTS;
  }
  return cache;
}

function write(next: Settings) {
  cache = next;
  localStorage.setItem(KEY, JSON.stringify(next));
  listeners.forEach((notify) => notify());
}

function subscribe(notify: () => void) {
  listeners.add(notify);
  const onStorage = (e: StorageEvent) => {
    if (e.key === KEY) {
      cache = null;
      notify();
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(notify);
    window.removeEventListener("storage", onStorage);
  };
}

export function useSettings(): Settings {
  return useSyncExternalStore(subscribe, read, () => DEFAULTS);
}

export function getSettings(): Settings {
  return read();
}

export function updateSettings(patch: Partial<Settings>) {
  write({ ...read(), ...patch });
}

export function replaceSettings(next: Partial<Settings>) {
  write({ ...DEFAULTS, ...next });
}
