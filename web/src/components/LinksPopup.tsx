"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

export type LinkEntry = {
  key: string;
  label: string; // nombre del producto (o del supermercado, en el menú de un producto)
  detail?: string; // texto más pequeño debajo del nombre
  price?: string; // sin precio: no está disponible
  url?: string | null;
  note?: string;
};

type Props = { title: string; entries: LinkEntry[]; className: string; hint: string; children: ReactNode };

// Botón que despliega una lista de enlaces.
export function LinksPopup({ title, entries, className, hint, children }: Props) {
  const btn = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  // La tabla tiene desplazamiento propio y recortaría el menú: por eso se coloca con position: fixed.
  const open = () => {
    if (pos) return setPos(null);
    const r = btn.current!.getBoundingClientRect();
    setPos({ top: r.bottom + 4, left: Math.max(8, Math.min(r.left, window.innerWidth - 348)) });
  };

  useEffect(() => {
    if (!pos) return;
    const close = () => setPos(null);
    // Desplazarse dentro del menú no debe cerrarlo; sí el resto de la página.
    const onScroll = (e: Event) => !menu.current?.contains(e.target as Node) && close();
    const outside = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!menu.current?.contains(t) && !btn.current?.contains(t)) close();
    };
    const escape = (e: KeyboardEvent) => e.key === "Escape" && close();
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", escape);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", escape);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", close);
    };
  }, [pos]);

  return (
    <>
      <button ref={btn} className={className} aria-haspopup="true" aria-expanded={!!pos} onClick={open} title={hint}>
        {children}
      </button>
      {pos && (
        <div ref={menu} className="links-menu" style={{ top: pos.top, left: pos.left }}>
          <strong>{title}</strong>
          <ul>
            {entries.map((e) => (
              <li key={e.key} className={e.price ? undefined : "off"}>
                <span className="links-name">
                  {e.url && e.price ? (
                    <a href={e.url} target="_blank" rel="noreferrer">
                      {e.label}
                    </a>
                  ) : (
                    <span>{e.label}</span>
                  )}
                  {e.detail && <span className="meta">{e.detail}</span>}
                </span>
                <span className="links-price">{e.price ?? e.note}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
