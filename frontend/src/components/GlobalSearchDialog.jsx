import React, { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { Search, X, Users, ShoppingBag, Kanban, Wrench, Shield, Clock } from "lucide-react";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { useAuth } from "@/contexts/AuthContext";

// iter169 — Recherche globale Cmd/Ctrl+K.
// Sécurité : le backend applique déjà cq(user) + perm_scope. Le composant se contente
// d'afficher ce qu'il reçoit et de journaliser les recherches récentes localement.
const RECENT_KEY_PREFIX = "kylot:search:recents:";
const MAX_RECENTS = 5;

const CAT_META = {
  clients: { label: "Clients", icon: Users, path: "/clients" },
  sales: { label: "Ventes", icon: ShoppingBag, path: "/ventes" },
  projects: { label: "Chantiers", icon: Kanban, path: "/chantiers" },
  reinterventions: { label: "Interventions", icon: Wrench, path: "/planning" },
  users: { label: "Utilisateurs", icon: Shield, path: "/utilisateurs" },
};

export default function GlobalSearchDialog({ open, onOpenChange }) {
  const nav = useNavigate();
  const { user } = useAuth();
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [recents, setRecents] = useState([]);
  const inputRef = useRef(null);
  const timerRef = useRef(null);
  const recentKey = `${RECENT_KEY_PREFIX}${user?.id || "anon"}`;

  useEffect(() => {
    if (!open) return;
    setQ(""); setResults(null);
    try { setRecents(JSON.parse(localStorage.getItem(recentKey) || "[]")); } catch (_) { setRecents([]); }
    setTimeout(() => inputRef.current?.focus(), 30);
  }, [open, recentKey]);

  useEffect(() => {
    if (!open) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    if (!q || q.trim().length < 2) { setResults(null); return; }
    timerRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const { data } = await api.get(`/search?q=${encodeURIComponent(q.trim())}&limit=8`);
        setResults(data);
      } catch (_) { setResults({ categories: {}, total: 0 }); }
      setLoading(false);
    }, 220);
    return () => timerRef.current && clearTimeout(timerRef.current);
  }, [q, open]);

  const commit = useCallback((query) => {
    if (!query) return;
    const list = [query, ...recents.filter((r) => r !== query)].slice(0, MAX_RECENTS);
    setRecents(list);
    try { localStorage.setItem(recentKey, JSON.stringify(list)); } catch (_) {}
  }, [recents, recentKey]);

  const openResult = (cat, item) => {
    commit(q);
    onOpenChange(false);
    const meta = CAT_META[cat];
    if (!meta) return;
    // iter190 — Ouvre la fiche directement quand on a un ID exploitable côté page cible.
    // Aujourd'hui : clients (page Clients ouvre le ClientDetailDialog via ?open=<id>).
    if (cat === "clients" && item?.id) {
      nav(`/clients?open=${encodeURIComponent(item.id)}`);
      return;
    }
    nav(meta.path);
  };

  const cats = results?.categories || {};
  const nothing = results && (results.total || 0) === 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* iter190 — Layout mobile : on ancre la dialog en HAUT de l'écran (top-2) pour que le
          champ de saisie et les résultats restent visibles au-dessus du clavier virtuel iOS.
          Sur desktop (sm:), on garde le centrage classique de Radix (`sm:top-[50%] sm:translate-y-[-50%]`). */}
      <DialogContent
        className="max-w-2xl p-0 overflow-hidden top-[8px] translate-y-0 sm:top-[50%] sm:-translate-y-1/2"
        data-testid="global-search-dialog"
      >
        <div className="flex items-center gap-2 px-4 border-b border-slate-200 sticky top-0 bg-white z-10">
          <Search size={18} className="text-slate-400" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Rechercher un client, chantier, vente…"
            className="flex-1 h-12 bg-transparent outline-none text-sm placeholder-slate-400"
            data-testid="global-search-input"
          />
          {q && <button onClick={() => setQ("")} className="p-1 text-slate-400 hover:text-slate-600"><X size={16} /></button>}
          <kbd className="hidden sm:inline text-[10px] uppercase tracking-widest text-slate-400 border border-slate-200 px-1.5 py-0.5 rounded">Esc</kbd>
        </div>

        {/* iter190 — Hauteur max différenciée : sur mobile on limite pour laisser la place
            au clavier virtuel (≈ 45vh). Sur desktop on garde 60vh comme avant. */}
        <div className="max-h-[45vh] sm:max-h-[60vh] overflow-y-auto py-2 overscroll-contain">
          {!q && recents.length > 0 && (
            <div className="px-2 pb-1">
              <p className="text-[10px] uppercase tracking-widest text-slate-400 px-3 py-2 flex items-center gap-1.5"><Clock size={12} /> Recherches récentes</p>
              {recents.map((r) => (
                <button key={r} onClick={() => setQ(r)} className="w-full text-left px-3 py-2 rounded-md hover:bg-slate-100 text-sm text-slate-700" data-testid={`recent-${r}`}>{r}</button>
              ))}
            </div>
          )}

          {loading && <p className="text-center text-xs text-slate-400 py-4">Recherche…</p>}

          {results && !loading && nothing && (
            <p className="text-center text-sm text-slate-500 py-6" data-testid="global-search-empty">Aucun résultat trouvé.</p>
          )}

          {results && !loading && !nothing && Object.entries(cats).map(([cat, items]) => {
            if (!items || !items.length) return null;
            const meta = CAT_META[cat];
            if (!meta) return null;
            const Icon = meta.icon;
            return (
              <div key={cat} className="px-2 pb-1">
                <p className="text-[10px] uppercase tracking-widest text-slate-400 px-3 py-2 flex items-center gap-1.5">
                  <Icon size={12} /> {meta.label} <span className="text-slate-300">({items.length})</span>
                </p>
                {items.map((it) => (
                  <button
                    key={`${cat}-${it.id}`}
                    onClick={() => openResult(cat, it)}
                    className="w-full text-left px-3 py-2 rounded-md hover:bg-slate-100 flex items-start gap-3"
                    data-testid={`result-${cat}-${it.id}`}
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-800 truncate">
                        {it.name || it.client_name || it.service || "—"}
                      </p>
                      <p className="text-xs text-slate-500 truncate">
                        {cat === "clients" && [it.city, it.postal_code, it.phone].filter(Boolean).join(" · ")}
                        {cat === "sales" && [it.service, it.commercial, it.sale_date, it.amount ? `${it.amount} €` : ""].filter(Boolean).join(" · ")}
                        {cat === "projects" && [it.city, it.status, (it.assigned_to || []).join(", "), it.scheduled_date].filter(Boolean).join(" · ")}
                        {cat === "reinterventions" && [it.reason, it.assigned_to, it.scheduled_date].filter(Boolean).join(" · ")}
                        {cat === "users" && [it.email, it.role].filter(Boolean).join(" · ")}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            );
          })}

          {!q && !recents.length && (
            <p className="text-center text-xs text-slate-400 py-8">Rechercher un client, chantier, vente, intervention, utilisateur…</p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
