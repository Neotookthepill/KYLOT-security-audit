import React, { useCallback, useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Loader2, Plus, Trash2, ChevronDown, ChevronRight, ArrowUp, ArrowDown, Check, AlertCircle } from "lucide-react";
import { toast } from "sonner";

// iter144 : gestionnaire des catégories clients (En cours, Réinter, Litiges…).
// Endpoints backend existants : GET/PUT /api/client-categories.
// Contraintes : ne pas supprimer une catégorie référencée par le mapping auto vente→client
//   (en_cours, litiges, annules, archives) pour éviter de casser la rétro-catégorisation.
const SYSTEM_KEYS = new Set(["en_cours", "litiges", "annules", "archives"]);

const COLOR_PALETTE = [
  { key: "indigo", dot: "bg-indigo-500", label: "Indigo" },
  { key: "sky", dot: "bg-sky-500", label: "Ciel" },
  { key: "orange", dot: "bg-orange-500", label: "Orange" },
  { key: "red", dot: "bg-red-500", label: "Rouge" },
  { key: "emerald", dot: "bg-emerald-500", label: "Vert" },
  { key: "slate", dot: "bg-slate-500", label: "Gris" },
  { key: "yellow", dot: "bg-yellow-500", label: "Jaune" },
  { key: "violet", dot: "bg-violet-500", label: "Violet" },
];

const genKey = (label) =>
  (label || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 40) || `cat_${Date.now().toString(36)}`;

function ColorPicker({ value, onChange }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center gap-1.5 h-8 px-2 rounded-md border border-slate-200 hover:border-slate-400 transition"
          title="Choisir la couleur"
          data-testid="cat-color-btn"
        >
          <span className={`h-3.5 w-3.5 rounded-full ${COLOR_PALETTE.find((c) => c.key === value)?.dot || "bg-slate-500"}`} />
          <span className="text-[11px] text-slate-500 capitalize">{value || "slate"}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-56 p-2" side="bottom" align="start">
        <div className="grid grid-cols-4 gap-1.5">
          {COLOR_PALETTE.map((c) => (
            <button
              key={c.key}
              type="button"
              onClick={() => onChange(c.key)}
              className={`h-7 w-7 rounded-full border-2 transition ${value === c.key ? "border-slate-900" : "border-transparent hover:border-slate-300"} ${c.dot}`}
              title={c.label}
              aria-label={c.label}
              data-testid={`cat-color-${c.key}`}
            />
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

export default function ClientCategoryManagerDialog({ open, onOpenChange, onSaved }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [expanded, setExpanded] = useState({}); // { idx: true }

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/client-categories");
      setRows((data || []).map((r) => ({
        key: r.key,
        label: r.label,
        color: r.color || "slate",
        order: r.order || 0,
        sub_statuses: Array.isArray(r.sub_statuses) ? r.sub_statuses.map((s) => ({ ...s })) : [],
      })));
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (open) load(); }, [open, load]);

  const updateRow = (idx, patch) => setRows((rs) => rs.map((r, i) => (i === idx ? { ...r, ...patch } : r)));

  const addRow = () => {
    setRows((rs) => [...rs, { key: `cat_${Date.now().toString(36)}`, label: "Nouvelle catégorie", color: "slate", order: rs.length + 1, sub_statuses: [], _new: true }]);
    setExpanded((e) => ({ ...e, [rows.length]: true }));
  };

  const removeRow = (idx) => {
    const r = rows[idx];
    if (SYSTEM_KEYS.has(r.key)) {
      if (!window.confirm(`« ${r.label} » est utilisée par la catégorisation automatique (statuts de vente).\nLa supprimer désactivera la rétro-catégorisation pour cette catégorie.\nContinuer ?`)) return;
    } else if (!window.confirm(`Supprimer la catégorie « ${r.label} » ?`)) return;
    setRows((rs) => rs.filter((_, i) => i !== idx));
  };

  const move = (idx, delta) => {
    setRows((rs) => {
      const next = rs.slice();
      const j = idx + delta;
      if (j < 0 || j >= next.length) return rs;
      [next[idx], next[j]] = [next[j], next[idx]];
      return next;
    });
  };

  const addSub = (catIdx) => {
    setRows((rs) => rs.map((r, i) => i === catIdx ? {
      ...r,
      sub_statuses: [...(r.sub_statuses || []), { key: `sub_${Date.now().toString(36)}`, label: "Nouveau sous-statut" }],
    } : r));
  };
  const updateSub = (catIdx, subIdx, patch) => {
    setRows((rs) => rs.map((r, i) => i === catIdx ? {
      ...r,
      sub_statuses: r.sub_statuses.map((s, k) => k === subIdx ? { ...s, ...patch } : s),
    } : r));
  };
  const removeSub = (catIdx, subIdx) => {
    setRows((rs) => rs.map((r, i) => i === catIdx ? {
      ...r,
      sub_statuses: r.sub_statuses.filter((_, k) => k !== subIdx),
    } : r));
  };

  const save = async () => {
    const clean = rows.map((r, i) => ({
      key: r.key && r.key.trim() ? r.key.trim() : genKey(r.label),
      label: (r.label || r.key || "").trim(),
      color: r.color || "slate",
      order: i + 1,
      sub_statuses: (r.sub_statuses || [])
        .filter((s) => (s.label || "").trim())
        .map((s) => ({ key: s.key && s.key.trim() ? s.key.trim() : genKey(s.label), label: s.label.trim() })),
    }));
    // Vérifs
    if (clean.some((c) => !c.label)) { toast.error("Chaque catégorie doit avoir un libellé."); return; }
    const keys = clean.map((c) => c.key);
    if (new Set(keys).size !== keys.length) { toast.error("Deux catégories ont la même clé."); return; }
    for (const c of clean) {
      const sk = c.sub_statuses.map((s) => s.key);
      if (new Set(sk).size !== sk.length) { toast.error(`« ${c.label} » : deux sous-statuts ont la même clé.`); return; }
    }
    setSaving(true);
    try {
      await api.put("/client-categories", { categories: clean });
      toast.success("Catégories enregistrées");
      onSaved?.();
      onOpenChange(false);
    } catch (err) {
      toast.error(formatApiError(err));
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!saving) onOpenChange(v); }}>
      <DialogContent className="sm:max-w-3xl max-h-[92vh] overflow-y-auto" data-testid="client-cat-manager-dialog">
        <DialogHeader>
          <DialogTitle>Gérer les catégories clients</DialogTitle>
          <p className="text-sm text-slate-500">
            Renommez, réordonnez, ajoutez ou supprimez vos catégories. Chaque catégorie peut avoir ses propres sous-statuts (ex. Réinter · À programmer / Programmé / Clos).
          </p>
        </DialogHeader>

        {loading && <div className="p-6 text-center text-slate-500"><Loader2 size={16} className="animate-spin inline mr-2" />Chargement…</div>}

        {!loading && (
          <>
            <div className="space-y-2 mt-2" data-testid="client-cat-list">
              {rows.map((r, idx) => {
                const isOpen = !!expanded[idx];
                const isSystem = SYSTEM_KEYS.has(r.key);
                return (
                  <div key={r.key + idx} className="border border-slate-200 rounded-lg bg-white overflow-hidden" data-testid={`client-cat-row-${r.key}`}>
                    <div className="flex items-center gap-2 p-2">
                      <button
                        type="button"
                        onClick={() => setExpanded((e) => ({ ...e, [idx]: !isOpen }))}
                        className="h-8 w-8 grid place-items-center rounded text-slate-400 hover:text-slate-900 hover:bg-slate-100"
                        title={isOpen ? "Masquer les sous-statuts" : "Afficher les sous-statuts"}
                        data-testid={`client-cat-toggle-${r.key}`}
                      >
                        {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                      </button>
                      <ColorPicker value={r.color} onChange={(c) => updateRow(idx, { color: c })} />
                      <Input
                        value={r.label}
                        onChange={(e) => updateRow(idx, { label: e.target.value })}
                        className="h-8 flex-1 min-w-0"
                        data-testid={`client-cat-label-${r.key}`}
                      />
                      {isSystem && (
                        <span
                          className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded border border-amber-200 bg-amber-50 text-amber-800 shrink-0"
                          title="Utilisée par la catégorisation automatique (statuts de vente)"
                        >
                          <AlertCircle size={10} /> Auto
                        </span>
                      )}
                      <span className="text-[10px] text-slate-400 shrink-0">
                        {r.sub_statuses?.length || 0} sous-statut{(r.sub_statuses?.length || 0) > 1 ? "s" : ""}
                      </span>
                      <div className="flex items-center gap-0.5 shrink-0">
                        <button type="button" onClick={() => move(idx, -1)} disabled={idx === 0}
                          className="h-8 w-8 grid place-items-center rounded text-slate-400 hover:text-slate-900 hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed"
                          title="Monter" data-testid={`client-cat-up-${r.key}`}
                        ><ArrowUp size={13} /></button>
                        <button type="button" onClick={() => move(idx, 1)} disabled={idx === rows.length - 1}
                          className="h-8 w-8 grid place-items-center rounded text-slate-400 hover:text-slate-900 hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed"
                          title="Descendre" data-testid={`client-cat-down-${r.key}`}
                        ><ArrowDown size={13} /></button>
                        <button type="button" onClick={() => removeRow(idx)}
                          className="h-8 w-8 grid place-items-center rounded text-slate-400 hover:text-red-600 hover:bg-red-50"
                          title="Supprimer" data-testid={`client-cat-remove-${r.key}`}
                        ><Trash2 size={13} /></button>
                      </div>
                    </div>
                    {isOpen && (
                      <div className="border-t border-slate-100 bg-slate-50/40 px-3 py-2 space-y-1.5" data-testid={`client-cat-subs-${r.key}`}>
                        {(r.sub_statuses || []).length === 0 && (
                          <p className="text-xs text-slate-400 italic">Aucun sous-statut. Cette catégorie sera un simple filtre.</p>
                        )}
                        {(r.sub_statuses || []).map((s, si) => (
                          <div key={s.key + si} className="flex items-center gap-2" data-testid={`client-sub-row-${r.key}-${si}`}>
                            <span className="text-[10px] text-slate-400 w-4 shrink-0">·</span>
                            <Input
                              value={s.label}
                              onChange={(e) => updateSub(idx, si, { label: e.target.value })}
                              className="h-7 flex-1 text-sm"
                              placeholder="Libellé du sous-statut"
                              data-testid={`client-sub-label-${r.key}-${si}`}
                            />
                            <button type="button" onClick={() => removeSub(idx, si)}
                              className="h-7 w-7 grid place-items-center rounded text-slate-400 hover:text-red-600 hover:bg-red-100"
                              title="Supprimer" data-testid={`client-sub-remove-${r.key}-${si}`}
                            ><Trash2 size={11} /></button>
                          </div>
                        ))}
                        <Button variant="ghost" size="sm" onClick={() => addSub(idx)} className="h-7 text-xs" data-testid={`client-sub-add-${r.key}`}>
                          <Plus size={11} className="mr-1" /> Ajouter un sous-statut
                        </Button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="mt-3">
              <Button variant="outline" size="sm" onClick={addRow} data-testid="client-cat-add">
                <Plus size={13} className="mr-1" /> Ajouter une catégorie
              </Button>
            </div>
          </>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>Annuler</Button>
          <Button onClick={save} disabled={saving || loading} data-testid="client-cat-save">
            {saving ? (<><Loader2 size={13} className="mr-1 animate-spin" /> Enregistrement…</>) : (<><Check size={13} className="mr-1" /> Enregistrer</>)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
