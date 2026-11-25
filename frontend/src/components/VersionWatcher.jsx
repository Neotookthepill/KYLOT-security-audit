import { useEffect, useRef, useState } from "react";
import { RefreshCw, X } from "lucide-react";

/** Détecte un nouveau build frontend et propose un rechargement.
 *  Utile quand une icône PWA ou un onglet reste sur une ancienne version.
 */
export default function VersionWatcher() {
  const [stale, setStale] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const initial = useRef(null);

  useEffect(() => {
    const script = [...document.scripts]
      .map((s) => s.src)
      .find((src) => /\/static\/js\/main\.[^/]+\.js$/.test(src));
    if (!script) return;
    initial.current = new URL(script, window.location.origin).pathname;
    let cancelled = false;

    const check = async () => {
      if (cancelled || dismissed) return;
      try {
        const r = await fetch(`/asset-manifest.json?v=${Date.now()}`, { cache: "no-store" });
        if (!r.ok) return;
        const m = await r.json();
        const latest = m?.files?.["main.js"];
        if (latest && initial.current && latest !== initial.current) setStale(true);
      } catch (_) { /* pas bloquant */ }
    };

    check();
    const timer = setInterval(check, 60_000);
    const onVisible = () => { if (document.visibilityState === "visible") check(); };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", check);
    return () => {
      cancelled = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", check);
    };
  }, [dismissed]);

  if (!stale || dismissed) return null;
  return (
    <div className="fixed inset-x-3 bottom-3 z-[100] mx-auto flex max-w-lg items-center gap-3 rounded-xl border border-primary/30 bg-card px-4 py-3 text-sm shadow-xl" role="status" data-testid="app-version-banner">
      <RefreshCw size={16} className="shrink-0 text-primary" />
      <span className="min-w-0 flex-1">Une nouvelle version de Qylot est disponible.</span>
      <button type="button" onClick={() => window.location.reload()} className="shrink-0 rounded-md bg-primary px-2.5 py-1.5 text-xs font-semibold text-primary-foreground">Recharger</button>
      <button type="button" onClick={() => setDismissed(true)} className="shrink-0 rounded p-1 text-muted-foreground hover:bg-muted" aria-label="Fermer"><X size={13} /></button>
    </div>
  );
}
