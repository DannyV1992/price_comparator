import { createClient } from "@libsql/client";

// Por ahora lee el SQLite que escribe `python -m sync.to_web`. Para publicar, apunta WEB_DATABASE_URL
// (y WEB_AUTH_TOKEN) a una base de Turso con las mismas tablas.
export const db = createClient({
  url: process.env.WEB_DATABASE_URL ?? "file:../data/web.db",
  authToken: process.env.WEB_AUTH_TOKEN,
});
