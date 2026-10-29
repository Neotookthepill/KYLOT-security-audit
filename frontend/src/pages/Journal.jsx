import React, { useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { History, RefreshCw } from "lucide-react";

const RESOURCE_LABELS = {
  sale: "Vente", client: "Client", project: "Chantier", user: "Utilisateur",
  overtime: "Heures sup", commission: "Commission", permissions: "Permissions",
};
const ACTION_LABELS = { create: "Création", update: "Modification", delete: "Suppression" };
const ACTION_CLS = {
  create: "bg-emerald-100 text-emerald-800",
  update: "bg-amber-100 text-amber-800",
  delete: "bg-red-100 text-red-800",
};

function fmtDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    return d.toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

function shorten(v) {
  if (v == null) return "—";
  if (typeof v === "string") return v.length > 120 ? v.slice(0, 120) + "…" : v;
  try {
    const s = JSON.stringify(v);
    return s.length > 200 ? s.slice(0, 200) + "…" : s;
  } catch { return String(v); }
}

export default function Journal() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState({});
  const [filters, setFilters] = useState({ user_id: "", action: "", resource: "", from_date: "", to_date: "" });
  const [usersMap, setUsersMap] = useState({});

  const load = async (override) => {
    const f = override || filters;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      Object.entries(f).forEach(([k, v]) => { if (v) params.append(k, v); });
      const [audit, users] = await Promise.all([
        api.get(`/audit?${params.toString()}`),
        api.get("/users").catch(() => ({ data: [] })),
      ]);
      setItems(audit.data || []);
      const m = {}; (users.data || []).forEach((u) => { m[u.id] = u.name || u.email; });
      setUsersMap(m);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setLoading(false); }
  };

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const userOptions = useMemo(() => Object.entries(usersMap).map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name)), [usersMap]);

  return (
    <div className="p-4 md:p-8 max-w-[1400px]">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
        <div>
          <p className="overline">Traçabilité</p>
          <h1 className="font-display text-3xl md:text-4xl font-semibold tracking-tight flex items-center gap-2">
            <History size={26} className="text-slate-500" />
            Journal d'activité
          </h1>
          <p className="text-sm text-slate-500 mt-2">Chaque action sensible (ventes, chantiers, clients, utilisateurs, heures sup, permissions) est enregistrée avec son auteur, la date et les valeurs modifiées.</p>
        </div>
        <Button variant="outline" onClick={load} disabled={loading} data-testid="journal-refresh">
          <RefreshCw size={14} className={`mr-1.5 ${loading ? "animate-spin" : ""}`} /> Actualiser
        </Button>
      </div>

      <Card className="border-slate-200 shadow-sm p-4 mb-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        <div>
          <label className="text-xs text-slate-500">Utilisateur</label>
          <Select value={filters.user_id || "__all"} onValueChange={(v) => setFilters({ ...filters, user_id: v === "__all" ? "" : v })}>
            <SelectTrigger className="h-9" data-testid="journal-filter-user"><SelectValue placeholder="Tous" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__all">Tous</SelectItem>
              {userOptions.map((u) => (<SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="text-xs text-slate-500">Type d'action</label>
          <Select value={filters.action || "__all"} onValueChange={(v) => setFilters({ ...filters, action: v === "__all" ? "" : v })}>
            <SelectTrigger className="h-9" data-testid="journal-filter-action"><SelectValue placeholder="Toutes" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__all">Toutes</SelectItem>
              <SelectItem value="create">Création</SelectItem>
              <SelectItem value="update">Modification</SelectItem>
              <SelectItem value="delete">Suppression</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="text-xs text-slate-500">Élément</label>
          <Select value={filters.resource || "__all"} onValueChange={(v) => setFilters({ ...filters, resource: v === "__all" ? "" : v })}>
            <SelectTrigger className="h-9" data-testid="journal-filter-resource"><SelectValue placeholder="Tous" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="__all">Tous</SelectItem>
              {Object.entries(RESOURCE_LABELS).map(([k, l]) => (<SelectItem key={k} value={k}>{l}</SelectItem>))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <label className="text-xs text-slate-500">Du</label>
          <Input type="date" value={filters.from_date} onChange={(e) => setFilters({ ...filters, from_date: e.target.value })} className="h-9" data-testid="journal-filter-from" />
        </div>
        <div>
          <label className="text-xs text-slate-500">Au</label>
          <Input type="date" value={filters.to_date} onChange={(e) => setFilters({ ...filters, to_date: e.target.value })} className="h-9" data-testid="journal-filter-to" />
        </div>
        <div className="sm:col-span-2 lg:col-span-5 flex justify-end gap-2">
          <Button variant="outline" size="sm" onClick={() => { const empty = { user_id: "", action: "", resource: "", from_date: "", to_date: "" }; setFilters(empty); load(empty); }} data-testid="journal-clear-filters">Réinitialiser</Button>
          <Button size="sm" onClick={load} data-testid="journal-apply-filters">Appliquer</Button>
        </div>
      </Card>

      <Card className="border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b border-slate-200 bg-slate-50/60">
                <th className="px-4 py-3 overline whitespace-nowrap">Date</th>
                <th className="px-4 py-3 overline whitespace-nowrap">Utilisateur</th>
                <th className="px-4 py-3 overline whitespace-nowrap">Action</th>
                <th className="px-4 py-3 overline whitespace-nowrap">Élément</th>
                <th className="px-4 py-3 overline">Détails</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 && !loading && (
                <tr><td colSpan={5} className="p-8 text-center text-slate-500">Aucune activité enregistrée pour ces filtres.</td></tr>
              )}
              {items.map((it) => {
                const isOpen = !!expanded[it.id];
                return (
                  <React.Fragment key={it.id}>
                    <tr className="border-b border-slate-100 hover:bg-slate-50/50 cursor-pointer" onClick={() => setExpanded({ ...expanded, [it.id]: !isOpen })} data-testid={`journal-row-${it.id}`}>
                      <td className="px-4 py-3 whitespace-nowrap text-slate-600">{fmtDate(it.at)}</td>
                      <td className="px-4 py-3 whitespace-nowrap font-medium">{it.user_name || usersMap[it.user_id] || "?"} <span className="text-xs text-slate-400">({it.user_role})</span></td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className={`inline-block px-2 py-0.5 rounded-md text-xs font-semibold ${ACTION_CLS[it.action] || "bg-slate-200 text-slate-700"}`}>
                          {ACTION_LABELS[it.action] || it.action}
                        </span>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">{RESOURCE_LABELS[it.resource] || it.resource}</td>
                      <td className="px-4 py-3 text-slate-600 truncate max-w-[400px]">
                        {it.action === "delete" && shorten(it.before?.name || it.before?.email || it.before?.service || it.resource_id)}
                        {it.action === "create" && shorten(it.after?.name || it.after?.email || it.after?.service || it.resource_id)}
                        {it.action === "update" && (it.resource === "permissions" ? "Permissions mises à jour" : shorten(it.after || it.resource_id))}
                      </td>
                    </tr>
                    {isOpen && (
                      <tr className="bg-slate-50/60 border-b border-slate-100" data-testid={`journal-detail-${it.id}`}>
                        <td colSpan={5} className="px-4 py-3">
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                            <div>
                              <p className="uppercase tracking-widest text-slate-500 mb-1">Avant</p>
                              <pre className="bg-white border border-slate-200 rounded p-2 overflow-auto max-h-64">{it.before ? JSON.stringify(it.before, null, 2) : "—"}</pre>
                            </div>
                            <div>
                              <p className="uppercase tracking-widest text-slate-500 mb-1">Après</p>
                              <pre className="bg-white border border-slate-200 rounded p-2 overflow-auto max-h-64">{it.after ? JSON.stringify(it.after, null, 2) : "—"}</pre>
                            </div>
                          </div>
                          <p className="text-[11px] text-slate-400 mt-2">ID élément : <span className="font-mono">{it.resource_id}</span></p>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
