"use client";

import { getList, replaceList, type ListItem } from "./list";
import { getSettings, replaceSettings, type Settings } from "./settings";

// Archivo con todo lo que llevo: la lista (con cantidades y reemplazos) y cómo tengo armada la comparación.
type Backup = { app: "comparador-super"; version: 1; savedAt: string; list: ListItem[]; settings: Settings };

export function downloadBackup() {
  const backup: Backup = {
    app: "comparador-super",
    version: 1,
    savedAt: new Date().toISOString(),
    list: getList(),
    settings: getSettings(),
  };
  const url = URL.createObjectURL(new Blob([JSON.stringify(backup, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `mi-lista-${backup.savedAt.slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(url);
}

// Devuelve cuántos productos tenía la lista cargada; lanza un error con un mensaje para mostrar si el archivo no sirve.
export async function loadBackup(file: File): Promise<number> {
  let data: Partial<Backup>;
  try {
    data = JSON.parse(await file.text()) as Partial<Backup>;
  } catch {
    throw new Error("El archivo no se pudo leer.");
  }
  if (data.app !== "comparador-super" || !Array.isArray(data.list)) {
    throw new Error("Este archivo no es una lista guardada de esta página.");
  }
  const list = data.list.filter(
    (i): i is ListItem => !!i && typeof i.productId === "string" && typeof i.name === "string" && i.qty > 0,
  );
  replaceList(list);
  replaceSettings(data.settings ?? {});
  return list.length;
}
