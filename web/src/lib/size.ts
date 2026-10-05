// Lee el tamaño de un producto a partir de su nombre («Arroz 1 kg», «Sopa 12 Unidades / 65 g / 2.3 oz»).
// Sirve para calcular cuánto costaría la cantidad de un producto en otro de distinto tamaño.

export type Size = {
  kind: "mass" | "volume" | "count";
  amount: number; // gramos, mililitros o unidades
  // Si el nombre trae cantidad y medida («3 Unidades / 2 kg»), se supone que la medida es la de cada unidad, pero
  // algunas tiendas la ponen como total: por eso se guarda el detalle para poder cambiar la interpretación.
  parts?: { count: number; each: number };
};

const NUMBER = "(\\d+(?:[.,]\\d+)?)";
const toNumber = (text: string) => Number(text.replace(",", "."));

// Primera medida en unidades métricas (si trae también onzas o libras, se ignoran).
const MEASURE = new RegExp(`(?<![\\d.,])${NUMBER}\\s*(kg|kilos?|gramos?|grs?|g|litros?|lts?|l|ml|cc)(?![a-zñ])`, "i");
const COUNT_AFTER = new RegExp(
  `(?<![\\d.,])${NUMBER}\\s*(?:unidades|unidad|unid|unds|uds|und|ud|un|pzas|piezas|rollos|sobres|tabletas|cápsulas|capsulas|bolsas|latas|botellas|pares)(?![a-zñ])`,
  "i",
);
// Productos que se venden por peso o volumen sin cantidad en el nombre («Cebolla Morada Kilo»): el precio es por 1 kg o 1 L.
const PER_KILO = /(?<![\d.,])\b(?:kilos?|kgs?|kilogramos?)\b/i;
const PER_LITER = /(?<![\d.,])\b(?:litros?|lts?)\b/i;
const PER_UNIT = /(?<![\d.,])\b(?:unidad|unid|und|ud)\b/i; // «Chile Dulce Unidad»: se vende de a una
const COUNT_X = /(?<![\d.,])(\d+)\s*x\s*(?=\d)/i; // «12 x 65 g»
const COUNT_PACK = /\b(?:pack|paquete|malla|caja|set)\s*(?:de\s*)?(\d+)\b/i;

const FACTORS: Record<string, { kind: "mass" | "volume"; factor: number }> = {
  kg: { kind: "mass", factor: 1000 },
  kilo: { kind: "mass", factor: 1000 },
  kilos: { kind: "mass", factor: 1000 },
  g: { kind: "mass", factor: 1 },
  gr: { kind: "mass", factor: 1 },
  grs: { kind: "mass", factor: 1 },
  gramo: { kind: "mass", factor: 1 },
  gramos: { kind: "mass", factor: 1 },
  l: { kind: "volume", factor: 1000 },
  lt: { kind: "volume", factor: 1000 },
  lts: { kind: "volume", factor: 1000 },
  litro: { kind: "volume", factor: 1000 },
  litros: { kind: "volume", factor: 1000 },
  ml: { kind: "volume", factor: 1 },
  cc: { kind: "volume", factor: 1 },
};

// Si el nombre trae cantidad y medida («12 Unidades / 65 g»), la medida es la de cada unidad.
export function parseSize(name: string | null | undefined): Size | null {
  if (!name) return null;
  const measure = MEASURE.exec(name);
  const count = Number(COUNT_X.exec(name)?.[1] ?? COUNT_AFTER.exec(name)?.[1] ?? COUNT_PACK.exec(name)?.[1] ?? 0);

  if (measure) {
    const unit = FACTORS[measure[2].toLowerCase()];
    const amount = toNumber(measure[1]) * unit.factor * (count > 1 ? count : 1);
    if (!(amount > 0)) return null;
    const each = toNumber(measure[1]) * unit.factor;
    return count > 1 ? { kind: unit.kind, amount, parts: { count, each } } : { kind: unit.kind, amount };
  }
  if (PER_KILO.test(name)) return { kind: "mass", amount: 1000 };
  if (PER_LITER.test(name)) return { kind: "volume", amount: 1000 };
  if (count > 0) return { kind: "count", amount: count };
  return PER_UNIT.test(name) ? { kind: "count", amount: 1 } : null;
}

// La misma presentación, pero tomando la medida que trae el nombre como el total y no como la de cada unidad.
export const asTotal = (size: Size): Size => (size.parts ? { kind: size.kind, amount: size.parts.each } : size);

export function formatSize(size: Size): string {
  const n = (v: number) => v.toLocaleString("es-CR", { maximumFractionDigits: 2 });
  if (size.parts) {
    const one = formatSize({ kind: size.kind, amount: size.parts.each });
    return `${size.parts.count} × ${one} = ${formatSize({ kind: size.kind, amount: size.amount })}`;
  }
  if (size.kind === "mass") return size.amount >= 1000 ? `${n(size.amount / 1000)} kg` : `${n(size.amount)} g`;
  if (size.kind === "volume") return size.amount >= 1000 ? `${n(size.amount / 1000)} L` : `${n(size.amount)} mL`;
  return `${n(size.amount)} ${size.amount === 1 ? "unidad" : "unidades"}`;
}

// Cuántos del producto `other` equivalen a una unidad del producto `own` (null si no se pueden comparar).
export function equivalentQty(own: Size | null, other: Size | null): number | null {
  if (!own || !other || own.kind !== other.kind) return null;
  const ratio = own.amount / other.amount;
  return Math.round(ratio * 10000) / 10000;
}

// Las cantidades de un reemplazo pueden ser fracciones: 1, 2, 0,25...
export const formatQty = (qty: number) => qty.toLocaleString("es-CR", { maximumFractionDigits: 3 });
