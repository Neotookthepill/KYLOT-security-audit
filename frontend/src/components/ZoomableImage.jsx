import React, { useCallback, useEffect, useRef, useState } from "react";
import { X, ZoomIn, ZoomOut, RotateCcw } from "lucide-react";

const clampScale = (s) => Math.max(1, Math.min(6, s));

// iter201 — Lightbox photo avec zoom (roulette, double-clic, pinch, +/-, drag pour panner).
// Utilisé dans ProjectDialog (chantiers / planning) et ReinterventionDialog.
export default function ZoomableImage({ src, onClose, testid = "zoom-image" }) {
  const safeSrc = typeof src === "string" && /^(?:https:\/\/|data:image\/(?:jpeg|jpg|png|webp);base64,)/i.test(src) ? src : "";
  const [scale, setScale] = useState(1);
  const [tx, setTx] = useState(0);
  const [ty, setTy] = useState(0);
  const dragRef = useRef({ dragging: false, x: 0, y: 0, sx: 0, sy: 0 });
  const pinchRef = useRef({ startDist: 0, startScale: 1 });
  const containerRef = useRef(null);

  const reset = useCallback(() => { setScale(1); setTx(0); setTy(0); }, []);
  const zoomIn = useCallback(() => setScale((s) => clampScale(s * 1.4)), []);
  const zoomOut = useCallback(() => {
    setScale((s) => {
      const next = clampScale(s / 1.4);
      if (next === 1) { setTx(0); setTy(0); }
      return next;
    });
  }, []);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") onClose?.();
      else if (e.key === "+" || e.key === "=") zoomIn();
      else if (e.key === "-") zoomOut();
      else if (e.key === "0") reset();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, reset, zoomIn, zoomOut]);

  const onWheel = (e) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    setScale((s) => {
      const next = clampScale(s * factor);
      if (next === 1) { setTx(0); setTy(0); }
      return next;
    });
  };

  const onDoubleClick = () => (scale === 1 ? setScale(2.5) : reset());

  const onMouseDown = (e) => {
    if (scale <= 1) return;
    dragRef.current = { dragging: true, x: e.clientX, y: e.clientY, sx: tx, sy: ty };
  };
  const onMouseMove = (e) => {
    if (!dragRef.current.dragging) return;
    setTx(dragRef.current.sx + (e.clientX - dragRef.current.x));
    setTy(dragRef.current.sy + (e.clientY - dragRef.current.y));
  };
  const onMouseUp = () => { dragRef.current.dragging = false; };

  // Pinch mobile (2 doigts)
  const dist = (t1, t2) => Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);
  const onTouchStart = (e) => {
    if (e.touches.length === 2) {
      pinchRef.current = { startDist: dist(e.touches[0], e.touches[1]), startScale: scale };
    } else if (e.touches.length === 1 && scale > 1) {
      const t = e.touches[0];
      dragRef.current = { dragging: true, x: t.clientX, y: t.clientY, sx: tx, sy: ty };
    }
  };
  const onTouchMove = (e) => {
    if (e.touches.length === 2) {
      e.preventDefault();
      const d = dist(e.touches[0], e.touches[1]);
      const ratio = d / (pinchRef.current.startDist || 1);
      setScale(clampScale(pinchRef.current.startScale * ratio));
    } else if (e.touches.length === 1 && dragRef.current.dragging) {
      const t = e.touches[0];
      setTx(dragRef.current.sx + (t.clientX - dragRef.current.x));
      setTy(dragRef.current.sy + (t.clientY - dragRef.current.y));
    }
  };
  const onTouchEnd = () => { dragRef.current.dragging = false; };

  if (!safeSrc) return null;

  return (
    <div
      ref={containerRef}
      className="fixed inset-0 z-[70] bg-black/90 flex items-center justify-center overflow-hidden select-none"
      onClick={(e) => { if (e.target === e.currentTarget) onClose?.(); }}
      onWheel={onWheel}
      onMouseMove={onMouseMove}
      onMouseUp={onMouseUp}
      onMouseLeave={onMouseUp}
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
      data-testid={testid}
    >
      <img
        src={safeSrc}
        alt="preview"
        draggable={false}
        onDoubleClick={onDoubleClick}
        onMouseDown={onMouseDown}
        style={{
          transform: `translate(${tx}px, ${ty}px) scale(${scale})`,
          transition: dragRef.current.dragging ? "none" : "transform 0.12s ease-out",
          cursor: scale > 1 ? (dragRef.current.dragging ? "grabbing" : "grab") : "zoom-in",
          touchAction: "none",
          maxHeight: "92vh",
          maxWidth: "92vw",
        }}
        className="rounded-md shadow-2xl"
      />
      {/* Contrôles */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-1.5 bg-white/95 rounded-full px-2 py-1.5 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <button onClick={zoomOut} className="p-1.5 rounded-full hover:bg-slate-100" aria-label="Dézoomer" data-testid="zoom-out"><ZoomOut size={16} /></button>
        <span className="text-xs tabular-nums text-slate-700 min-w-[42px] text-center">{Math.round(scale * 100)}%</span>
        <button onClick={zoomIn} className="p-1.5 rounded-full hover:bg-slate-100" aria-label="Zoomer" data-testid="zoom-in"><ZoomIn size={16} /></button>
        <div className="w-px h-4 bg-slate-200 mx-1" />
        <button onClick={reset} className="p-1.5 rounded-full hover:bg-slate-100" aria-label="Réinitialiser" data-testid="zoom-reset"><RotateCcw size={14} /></button>
      </div>
      <button className="absolute top-4 right-4 bg-white/95 rounded-full p-2 shadow-xl" onClick={onClose} aria-label="Fermer" data-testid="zoom-close"><X size={16} /></button>
      <p className="absolute top-4 left-4 text-white/70 text-xs">Double-clic / roulette / pincer pour zoomer · Esc pour fermer</p>
    </div>
  );
}
