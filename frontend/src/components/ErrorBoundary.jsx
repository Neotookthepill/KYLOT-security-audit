import React from "react";

/**
 * Isolates a subtree from the rest of the app.
 * If anything inside throws, we render a small fallback and DO NOT
 * bubble the error up (so the main app keeps working, the user stays
 * logged in, and no white-screen crash can occur).
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, msg: "" };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, msg: (error && error.message) || "" };
  }
  componentDidCatch(error, info) {
    try { console.error("ErrorBoundary caught:", error, info); } catch (_) {}
    // iter54: si un chunk JS n'a pas pu se charger après une republication
    // (nouveau bundle, ancien index.html en cache), on force un rechargement
    // "hard" pour récupérer le nouveau HTML + chunks.
    try {
      const msg = String((error && error.message) || "");
      const isChunkFail = /ChunkLoadError|Loading chunk .* failed|Failed to fetch dynamically imported module/i.test(msg);
      if (isChunkFail && typeof window !== "undefined" && !sessionStorage.getItem("kylot_chunk_reloaded")) {
        sessionStorage.setItem("kylot_chunk_reloaded", "1");
        window.location.reload();
      }
    } catch (_) {}
  }
  reset = () => this.setState({ hasError: false, msg: "" });
  render() {
    if (this.state.hasError) {
      const Fallback = this.props.fallback;
      if (Fallback) return <Fallback message={this.state.msg} reset={this.reset} />;
      return null; // never crash the whole app
    }
    return this.props.children;
  }
}

/**
 * iter54: Fallback plein écran pour la racine de l'app.
 * Utilisé par <ErrorBoundary fallback={AppErrorFallback}> autour de <AppRoutes/>.
 * Ne dépend d'aucun contexte (AuthContext / SettingsContext peuvent avoir crashé).
 */
export function AppErrorFallback({ message, reset }) {
  const goHome = () => {
    try { sessionStorage.clear(); } catch (_) {}
    try { window.location.assign("/"); } catch (_) { reset?.(); }
  };
  const hardReload = () => {
    try {
      // Nettoie le cache navigateur qui garde parfois un ancien bundle
      if (typeof caches !== "undefined") { caches.keys().then((ks) => ks.forEach((k) => caches.delete(k))); }
    } catch (_) {}
    try { window.location.reload(); } catch (_) { reset?.(); }
  };
  const disconnect = () => {
    try {
      Object.keys(localStorage).forEach((k) => {
        if (k.startsWith("kylot") || k.includes("token")) localStorage.removeItem(k);
      });
      sessionStorage.clear();
    } catch (_) {}
    try { window.location.assign("/login"); } catch (_) { reset?.(); }
  };
  // iter55: rapport de bug — copie un mini-rapport dans le presse-papier
  const [copied, setCopied] = React.useState(false);
  const reportBug = () => {
    try {
      const report = [
        `QYLOT · rapport d'erreur`,
        `Date : ${new Date().toISOString()}`,
        `URL  : ${window.location.href}`,
        `UA   : ${navigator.userAgent}`,
        `Msg  : ${message || "(inconnu)"}`,
      ].join("\n");
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(report).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 2500);
        });
      } else {
        const ta = document.createElement("textarea");
        ta.value = report; document.body.appendChild(ta);
        ta.select(); document.execCommand("copy"); document.body.removeChild(ta);
        setCopied(true);
        setTimeout(() => setCopied(false), 2500);
      }
    } catch (_) {}
  };
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-6" data-testid="app-error-fallback">
      <div className="max-w-md w-full bg-white border border-slate-200 rounded-2xl shadow-sm p-6 text-center">
        <div className="mx-auto h-12 w-12 rounded-full bg-red-50 grid place-items-center mb-3">
          <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-red-600" aria-hidden="true"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
        </div>
        <h1 className="font-display text-xl font-semibold text-slate-900">Oups, l'application a rencontré un problème</h1>
        <p className="text-sm text-slate-500 mt-1">
          Rassure-toi : rien n'est perdu — tes ventes, chantiers et données sont bien sauvegardés côté serveur.
        </p>
        {message && (
          <details className="text-left mt-3 border border-slate-100 rounded-lg bg-slate-50 p-2">
            <summary className="text-[11px] text-slate-500 cursor-pointer">Détail technique</summary>
            <p className="text-[11px] font-mono text-slate-600 mt-1 break-words">{message}</p>
          </details>
        )}
        <div className="mt-5 flex flex-col gap-2">
          <button type="button" onClick={hardReload} className="w-full h-10 rounded-lg bg-slate-900 text-white text-sm font-semibold hover:bg-slate-800 transition" data-testid="app-error-reload">
            Réessayer (recharger l'app)
          </button>
          <button type="button" onClick={goHome} className="w-full h-10 rounded-lg border border-slate-300 text-sm font-medium text-slate-700 hover:bg-slate-100 transition" data-testid="app-error-home">
            Revenir au tableau de bord
          </button>
          <button type="button" onClick={disconnect} className="w-full h-10 rounded-lg text-sm text-slate-500 hover:text-slate-800 transition" data-testid="app-error-logout">
            Se déconnecter et repartir de zéro
          </button>
          <button
            type="button"
            onClick={reportBug}
            className="w-full h-9 rounded-lg text-[11px] text-slate-400 hover:text-slate-700 transition inline-flex items-center justify-center gap-1.5"
            data-testid="app-error-report"
          >
            {copied ? (
              <>
                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-emerald-600"><polyline points="20 6 9 17 4 12"/></svg>
                Rapport copié — collez-le dans un email au support
              </>
            ) : (
              <>
                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
                Copier un rapport de bug
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
