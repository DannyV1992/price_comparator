"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

// Las fotos vienen de los sitios de cada tienda, en muchos dominios: se usa <img> en vez de next/image.
// Al hacer clic, la foto se ve grande; se cierra con otro clic o con Escape.
export function Thumb({ src, alt }: { src: string | null; alt: string }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation(); // que no cierre también el cuadro que esté detrás
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [open]);

  if (!src) return <div className="thumb thumb-empty" aria-hidden="true" />;

  return (
    <>
      <button
        className="thumb-btn"
        onClick={() => setOpen(true)}
        aria-label={`Ampliar foto de ${alt}`}
        title="Ampliar foto"
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img className="thumb" src={src} alt={alt} loading="lazy" referrerPolicy="no-referrer" />
      </button>
      {open &&
        createPortal(
          <div
            className="lightbox"
            role="dialog"
            aria-modal="true"
            aria-label={alt}
            onClick={(e) => {
              e.stopPropagation(); // los eventos de un portal suben al componente padre
              setOpen(false);
            }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={src} alt={alt} referrerPolicy="no-referrer" />
            <p>{alt}</p>
          </div>,
          document.body,
        )}
    </>
  );
}
