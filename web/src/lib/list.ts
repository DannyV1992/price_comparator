"use client";

import { useSyncExternalStore } from "react";

// Producto de otra marca o presentación que se usa en una tienda cuando el elegido está agotado allí.
export type Substitute = { productId: string; name: string };

export type ListItem = {
  productId: string;
  name: string;
  brand: string | null;
  imageUrl: string | null;
  qty: number;
  subs?: Record<string, Substitute>; // id de la tienda -> reemplazo en esa tienda
};

// La lista vive en el navegador (localStorage): sin cuentas ni base de datos.
const KEY = "mi-lista-v1";
const EMPTY: ListItem[] = [];
const listeners = new Set<() => void>();
let cache: ListItem[] | null = null;

function read(): ListItem[] {
  if (cache) return cache;
  try {
    cache = JSON.parse(localStorage.getItem(KEY) ?? "[]") as ListItem[];
  } catch {
    cache = [];
  }
  return cache;
}

function write(items: ListItem[]) {
  cache = items;
  localStorage.setItem(KEY, JSON.stringify(items));
  listeners.forEach((notify) => notify());
}

function subscribe(notify: () => void) {
  listeners.add(notify);
  // Si la lista cambia en otra pestaña, se recarga.
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

export function useList(): ListItem[] {
  return useSyncExternalStore(subscribe, read, () => EMPTY);
}

export function addItem(item: Omit<ListItem, "qty" | "subs">) {
  const items = read();
  const found = items.find((i) => i.productId === item.productId);
  write(
    found
      ? items.map((i) => (i.productId === item.productId ? { ...i, qty: i.qty + 1 } : i))
      : [...items, { ...item, qty: 1 }],
  );
}

export function setQty(productId: string, qty: number) {
  write(
    qty <= 0
      ? read().filter((i) => i.productId !== productId)
      : read().map((i) => (i.productId === productId ? { ...i, qty } : i)),
  );
}

export function removeItem(productId: string) {
  write(read().filter((i) => i.productId !== productId));
}

export function clearList() {
  write([]);
}

// Pone (o quita, con null) el reemplazo de un producto en una tienda.
export function setSubstitute(productId: string, storeId: number, sub: Substitute | null) {
  write(
    read().map((item) => {
      if (item.productId !== productId) return item;
      const subs = { ...item.subs };
      if (sub) subs[String(storeId)] = sub;
      else delete subs[String(storeId)];
      return { ...item, subs };
    }),
  );
}
