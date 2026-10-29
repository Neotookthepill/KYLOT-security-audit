import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog";
import { toast } from "sonner";
import { Search, Trash2, Upload, X, Pencil } from "lucide-react";
import ClientDetailDialog from "@/components/ClientDetailDialog";
import BulkImportClientsDialog from "@/components/BulkImportClientsDialog";
import ImportClientsFileDialog from "@/components/ImportClientsFileDialog";
import ClientCategoryManagerDialog from "@/components/ClientCategoryManagerDialog";
import { useAuth } from "@/contexts/AuthContext";

const empty = { name: "", phone: "", email: "", address: "", postal_code: "", city: "", notes: "" };

const CAT_COLORS = {
  indigo: { chip: "bg-indigo-100 text-indigo-800 border-indigo-300", active: "bg-indigo-600 text-white border-indigo-600" },
  sky: { chip: "bg-sky-100 text-sky-800 border-sky-300", active: "bg-sky-600 text-white border-sky-600" },
  orange: { chip: "bg-orange-100 text-orange-800 border-orange-300", active: "bg-orange-600 text-white border-orange-600" },
  red: { chip: "bg-red-100 text-red-800 border-red-300", active: "bg-red-600 text-white border-red-600" },
  emerald: { chip: "bg-emerald-100 text-emerald-800 border-emerald-300", active: "bg-emerald-600 text-white border-emerald-600" },
  slate: { chip: "bg-slate-100 text-slate-700 border-slate-300", active: "bg-slate-900 text-white border-slate-900" },
  yellow: { chip: "bg-yellow-100 text-yellow-800 border-yellow-300", active: "bg-yellow-600 text-white border-yellow-600" },
  violet: { chip: "bg-violet-100 text-violet-800 border-violet-300", active: "bg-violet-600 text-white border-violet-600" },
};
const clsFor = (color, active) => (CAT_COLORS[color] || CAT_COLORS.slate)[active ? "active" : "chip"];

export default function Clients() {
  const { can } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [clients, setClients] = useState([]);
  const [categories, setCategories] = useState([]);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [fileImportOpen, setFileImportOpen] = useState(false);
  const [catManagerOpen, setCatManagerOpen] = useState(false);
  const [form, setForm] = useState(empty);
  const [selected, setSelected] = useState(null);
  const [saving, setSaving] = useState(false);
  const [activeCat, setActiveCat] = useState("all"); // "all" | category_key
  const [activeSub, setActiveSub] = useState("all"); // "all" | sub_status_key

  const load = async () => {
    const [c, cats] = await Promise.all([api.get("/clients"), api.get("/client-categories").catch(() => ({ data: [] }))]);
    setClients(c.data);
    setCategories(cats.data || []);
  };
  useEffect(() => { load(); }, []);

  // iter190 — Ouverture directe de la fiche client via ?open=<client_id>.
  // Utilisé par la recherche globale mobile pour que taper un client → ouvrir la fiche
  // se fasse en un seul geste (pas seulement naviguer vers /clients).
  useEffect(() => {
    const openId = searchParams.get("open");
    if (!openId || !clients.length) return;
    const c = clients.find((x) => x.id === openId);
    if (c) {
      setSelected(c);
      // On retire le param de l'URL pour que le back-button ne reboucle pas dessus.
      const next = new URLSearchParams(searchParams);
      next.delete("open");
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, clients, setSearchParams]);

  const create = async () => {
    if (saving) return;
    if (!form.name.trim()) return toast.error("Nom requis");
    setSaving(true);
    try {
      await api.post("/clients", form);
      toast.success("Client ajouté");
      setForm(empty); setOpen(false); load();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setSaving(false); }
  };

  const remove = async (id) => {
    if (!window.confirm("Supprimer ce client ?")) return;
    try {
      await api.delete(`/clients/${id}`);
      toast.success("Client supprimé"); load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const assignCategory = async (client, category_key, sub_status_key, action = "set") => {
    try {
      const { data } = await api.put(`/clients/${client.id}/category`, { category_key, sub_status_key, action });
      setClients((prev) => prev.map((c) => (c.id === client.id ? data : c)));
      toast.success(action === "remove" ? "Catégorie retirée" : "Catégorie mise à jour");
    } catch (err) { toast.error(formatApiError(err)); }
  };

  // Compute counts per category from all clients (regardless of current filter)
  const counts = useMemo(() => {
    const m = { all: clients.length };
    for (const cat of categories) m[cat.key] = 0;
    for (const c of clients) for (const cc of (c.categories || [])) if (m[cc.category_key] !== undefined) m[cc.category_key]++;
    return m;
  }, [clients, categories]);

  const activeCategory = categories.find((c) => c.key === activeCat);

  // Filter clients by search + active cat/sub
  const filtered = useMemo(() => {
    const s = q.toLowerCase();
    return clients.filter((c) => {
      const matchQ = `${c.name} ${c.phone} ${c.address} ${c.email} ${c.city} ${c.postal_code}`.toLowerCase().includes(s);
      if (!matchQ) return false;
      if (activeCat === "all") return true;
      const hit = (c.categories || []).find((cc) => cc.category_key === activeCat);
      if (!hit) return false;
      if (activeSub === "all") return true;
      return hit.sub_status_key === activeSub;
    });
  }, [clients, q, activeCat, activeSub]);

  return (
    <div className="p-4 md:p-8 max-w-[1400px]">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
        <div>
          <p className="overline">Répertoire</p>
          <h1 className="font-display text-3xl md:text-4xl font-semibold tracking-tight">Clients</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          {can("clients", "create") && (
            <>
              <Button variant="outline" onClick={() => setFileImportOpen(true)} data-testid="file-import-btn">
                <Upload size={14} className="mr-1.5" /> Importer un fichier
              </Button>
              <Button variant="outline" onClick={() => setBulkOpen(true)} data-testid="bulk-import-btn">
                <Upload size={14} className="mr-1.5" /> Import copier-coller
              </Button>
              <Dialog open={open} onOpenChange={setOpen}>
                <DialogTrigger asChild><Button data-testid="new-client-btn">+ Nouveau client</Button></DialogTrigger>
                <DialogContent className="sm:max-w-md" data-testid="new-client-dialog">
                  <DialogHeader><DialogTitle className="font-display text-2xl">Nouveau client</DialogTitle></DialogHeader>
                  <div className="space-y-3">
                    <div><Label>Nom / Prénom</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="client-name-input" /></div>
                    <div><Label>Téléphone</Label><Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></div>
                    <div><Label>Email</Label><Input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
                    <div><Label>Adresse</Label><Input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></div>
                    <div className="grid grid-cols-[120px_1fr] gap-2">
                      <div><Label>Code postal</Label><Input value={form.postal_code} onChange={(e) => setForm({ ...form, postal_code: e.target.value })} /></div>
                      <div><Label>Ville</Label><Input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} /></div>
                    </div>
                    <div><Label>Notes</Label><Textarea rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></div>
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setOpen(false)}>Annuler</Button>
                    <Button onClick={create} disabled={saving} data-testid="client-submit-btn">{saving ? "Enregistrement…" : "Enregistrer"}</Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </>
          )}
        </div>
      </div>

      <BulkImportClientsDialog open={bulkOpen} onOpenChange={setBulkOpen} onImported={load} />
      <ImportClientsFileDialog open={fileImportOpen} onOpenChange={setFileImportOpen} onImported={load} />
      <ClientCategoryManagerDialog open={catManagerOpen} onOpenChange={setCatManagerOpen} onSaved={load} />

      {/* iter133 : catégories principales */}
      <div className="mb-3 flex flex-wrap items-center gap-2" data-testid="client-categories-bar">
        <button
          type="button"
          onClick={() => { setActiveCat("all"); setActiveSub("all"); }}
          className={`h-9 px-4 rounded-full text-sm font-medium border transition ${activeCat === "all" ? clsFor("slate", true) : "bg-white border-slate-200 text-slate-700 hover:bg-slate-50"}`}
          data-testid="client-cat-all"
        >
          Tous <span className="ml-1.5 text-xs opacity-70">({counts.all})</span>
        </button>
        {categories.map((c) => (
          <button
            key={c.key}
            type="button"
            onClick={() => { setActiveCat(c.key); setActiveSub("all"); }}
            className={`h-9 px-4 rounded-full text-sm font-medium border transition ${activeCat === c.key ? clsFor(c.color, true) : `${clsFor(c.color, false)} hover:brightness-95`}`}
            data-testid={`client-cat-${c.key}`}
          >
            {c.label} <span className="ml-1.5 text-xs opacity-70">({counts[c.key] || 0})</span>
          </button>
        ))}
        {can("settings", "modify") && (
          <button
            type="button"
            onClick={() => setCatManagerOpen(true)}
            className="h-9 w-9 grid place-items-center rounded-full border border-dashed border-slate-300 text-slate-500 hover:text-slate-900 hover:border-slate-900 hover:bg-slate-50 transition ml-1"
            title="Gérer les catégories (ajouter / renommer / supprimer)"
            data-testid="client-cat-manage-btn"
            aria-label="Gérer les catégories"
          >
            <Pencil size={13} />
          </button>
        )}
      </div>

      {/* iter133 : sous-statuts (visibles uniquement quand une catégorie est sélectionnée et qu'elle en a) */}
      {activeCategory && activeCategory.sub_statuses && activeCategory.sub_statuses.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-1.5 pl-2 border-l-2 border-slate-200" data-testid="client-substatus-bar">
          <button
            type="button"
            onClick={() => setActiveSub("all")}
            className={`h-7 px-3 rounded-md text-xs font-medium transition ${activeSub === "all" ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"}`}
            data-testid="client-sub-all"
          >
            Tous
          </button>
          {activeCategory.sub_statuses.map((s) => (
            <button
              key={s.key}
              type="button"
              onClick={() => setActiveSub(s.key)}
              className={`h-7 px-3 rounded-md text-xs font-medium transition ${activeSub === s.key ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"}`}
              data-testid={`client-sub-${s.key}`}
            >
              {s.label}
            </button>
          ))}
        </div>
      )}

      <Card className="border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-200 flex items-center gap-3">
          <Search size={16} className="text-slate-400" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher…" className="border-0 shadow-none focus-visible:ring-0 h-9 px-0" />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b border-slate-200 bg-slate-50/60">
                <th className="px-5 py-3 overline">Nom / Prénom</th>
                <th className="px-5 py-3 overline">Téléphone</th>
                <th className="px-5 py-3 overline">Adresse</th>
                <th className="px-5 py-3 overline">CP</th>
                <th className="px-5 py-3 overline">Ville</th>
                <th className="px-5 py-3 overline">Catégories</th>
                <th className="px-5 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && <tr><td colSpan={7} className="p-8 text-center text-slate-500">Aucun client.</td></tr>}
              {filtered.map((c) => (
                <tr key={c.id} className="data-row border-b border-slate-100 cursor-pointer" onClick={() => setSelected(c)} data-testid={`client-row-${c.id}`}>
                  <td className="px-5 py-3 font-semibold text-slate-900">{c.name}</td>
                  <td className="px-5 py-3">{c.phone}</td>
                  <td className="px-5 py-3 text-slate-600">{c.address}</td>
                  <td className="px-5 py-3">{c.postal_code}</td>
                  <td className="px-5 py-3">{c.city}</td>
                  <td className="px-5 py-3" onClick={(e) => e.stopPropagation()}>
                    <div className="flex flex-wrap items-center gap-1">
                      {(c.categories || []).map((cc) => {
                        const cat = categories.find((x) => x.key === cc.category_key);
                        if (!cat) return null;
                        const sub = (cat.sub_statuses || []).find((s) => s.key === cc.sub_status_key);
                        return (
                          <span key={cc.category_key} className={`inline-flex items-center gap-1 h-6 px-2 rounded-md text-[10.5px] font-medium border ${clsFor(cat.color, false)}`} data-testid={`client-badge-${c.id}-${cat.key}`}>
                            {cat.label}{sub ? ` · ${sub.label}` : ""}
                            <button type="button" onClick={() => assignCategory(c, cc.category_key, null, "remove")} className="opacity-60 hover:opacity-100" aria-label="Retirer"><X size={10} /></button>
                          </span>
                        );
                      })}
                      {can("clients", "edit") && (
                        <select
                          onChange={(e) => {
                            const v = e.target.value;
                            e.target.value = "";
                            if (!v) return;
                            const [ck, sk] = v.split("|");
                            assignCategory(c, ck, sk || null, "set");
                          }}
                          className="h-6 px-1.5 rounded-md text-[10.5px] border border-dashed border-slate-300 bg-white text-slate-500 hover:border-slate-500"
                          data-testid={`client-assign-${c.id}`}
                          defaultValue=""
                        >
                          <option value="">+ Ajouter</option>
                          {categories.map((cat) => (
                            (cat.sub_statuses && cat.sub_statuses.length)
                              ? <optgroup key={cat.key} label={cat.label}>
                                  <option value={`${cat.key}|`}>{cat.label} (sans sous-statut)</option>
                                  {cat.sub_statuses.map((s) => (
                                    <option key={s.key} value={`${cat.key}|${s.key}`}>{cat.label} · {s.label}</option>
                                  ))}
                                </optgroup>
                              : <option key={cat.key} value={`${cat.key}|`}>{cat.label}</option>
                          ))}
                        </select>
                      )}
                    </div>
                  </td>
                  <td className="px-5 py-3 text-right">
                    {can("clients", "delete") && (
                      <Button variant="ghost" size="sm" onClick={(e) => { e.stopPropagation(); remove(c.id); }} data-testid={`client-delete-${c.id}`} aria-label="Supprimer">
                        <Trash2 size={14} />
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <ClientDetailDialog client={selected} open={!!selected} onOpenChange={(v) => !v && setSelected(null)} />
    </div>
  );
}
