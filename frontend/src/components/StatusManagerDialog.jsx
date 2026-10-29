import React, { useEffect, useMemo, useState, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";
import { GripVertical, Plus, Trash2, Loader2, Check, RotateCcw, EyeOff } from "lucide-react";
import { toast } from "sonner";
import { STATUS_COLORS, clsFromColor } from "@/lib/saleConstants";

const genValue = (label) =>
  (label || "")
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 40) || `stat_${Date.now().toString(36)}`;

function ColorPicker({ value, onChange, disabled }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          disabled={disabled}
          className="inline-flex items-center gap-1.5 h-8 px-2 rounded-md border border-slate-200 hover:border-slate-400 transition"
          title="Choisir la couleur"
          data-testid="status-color-btn"
        >
          <span className={`h-3.5 w-3.5 rounded-full ${STATUS_COLORS.find((c) => c.key === value)?.dot || "bg-slate-500"}`} />
          <span className="text-[11px] text-slate-500 capitalize">{value}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-56 p-2" side="bottom" align="start">
        <div className="grid grid-cols-6 gap-1.5">
          {STATUS_COLORS.map((c) => (
            <button
              key={c.key}
              type="button"
              onClick={() => onChange(c.key)}
              className={`h-7 w-7 rounded-full border-2 transition ${value === c.key ? "border-slate-900" : "border-transparent hover:border-slate-300"} ${c.dot}`}
              title={c.label}
              aria-label={c.label}
              data-testid={`status-color-${c.key}`}
            />
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

export default function StatusManagerDialog({ open, onOpenChange, onSaved }) {
  const [rows, setRows] = useState([]);
  const [usage, setUsage] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dragging, setDragging] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [rl, ru] = await Promise.all([api.get("/sale-statuses"), api.get("/sale-statuses/usage")]);
      setRows((rl.data || []).map((r) => ({ ...r })));
      setUsage(ru.data || {});
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (open) load(); }, [open, load]);

  const updateRow = (idx, patch) => {
    setRows((rs) => rs.map((r, i) => (i === idx ? { ...r, ...patch } : r)));
  };
  const removeRow = async (idx) => {
    const r = rows[idx];
    if (r.system) { toast.error("Statut système : vous pouvez le désactiver mais pas le supprimer."); return; }
    const inUse = (usage[r.value] || 0) > 0;
    if (!inUse) { setRows((rs) => rs.filter((_, i) => i !== idx)); return; }
    // iter103 : réaffectation obligatoire avant suppression — l'admin choisit vers quel statut
    const candidates = rows.filter((x) => x.value !== r.value && x.active !== false && x.value);
    if (candidates.length === 0) { toast.error("Aucun autre statut actif disponible pour réaffecter."); return; }
    const labels = candidates.map((c, i) => `${i + 1}. ${c.label} (${c.value})`).join("\n");
    const answer = window.prompt(`« ${r.label} » est utilisé par ${usage[r.value]} vente(s).\nVers quel statut voulez-vous les réaffecter ? Tapez le numéro :\n\n${labels}`);
    if (!answer) return;
    const idxPicked = parseInt(String(answer).trim(), 10) - 1;
    const target = candidates[idxPicked];
    if (!target) { toast.error("Choix invalide"); return; }
    try {
      const res = await api.post("/sale-statuses/reassign", { source: r.value, target: target.value });
      toast.success(`${res.data.reassigned} vente(s) réaffectée(s) vers « ${target.label} »`);
      onSaved?.();
      await load();
    } catch (err) { toast.error(formatApiError(err)); }
  };
  const addRow = () => {
    setRows((rs) => [...rs, { value: `stat_${Date.now().toString(36)}`, label: "Nouveau statut", color: "slate", active: true, system: false, _new: true }]);
  };
  const resetDefaults = () => {
    if (!window.confirm("Réinitialiser à l'ordre + couleurs QYLOT recommandés ? (aucune vente n'est modifiée)")) return;
    setRows([
      { value: "attente_prog", label: "En attente prog", color: "violet", active: true, system: true, hides_from_projects: false },
      { value: "attente_fi", label: "En attente FI", color: "orange", active: true, system: true, hides_from_projects: false },
      { value: "en_cours", label: "PROG", color: "indigo", active: true, system: true, hides_from_projects: false },
      { value: "chantier_fini", label: "Chantier fini", color: "yellow", active: true, system: true, hides_from_projects: false },
      { value: "commercial_cheque", label: "Commercial a le chèque", color: "sky", active: true, system: true, hides_from_projects: false },
      { value: "argent_recupere", label: "Chèque récupéré", color: "emerald", active: true, system: true, hides_from_projects: false },
      { value: "litige", label: "Litige", color: "orange", active: true, system: true, hides_from_projects: true },
      { value: "annule", label: "Annulé", color: "red", active: true, system: true, hides_from_projects: true },
    ]);
  };

  const onDragStart = (idx) => setDragging(idx);
  const onDragOver = (e) => e.preventDefault();
  const onDrop = (idx) => {
    if (dragging == null || dragging === idx) return;
    setRows((rs) => {
      const next = rs.slice();
      const [it] = next.splice(dragging, 1);
      next.splice(idx, 0, it);
      return next;
    });
    setDragging(null);
  };

  const save = async () => {
    // Auto-fix values for new rows
    const clean = rows.map((r) => ({
      value: r.value || genValue(r.label),
      label: r.label || r.value,
      color: r.color || "slate",
      active: r.active !== false,
      default: !!r.default,
      hides_from_projects: !!r.hides_from_projects,
    }));
    // Detect duplicate values
    const vs = clean.map((r) => r.value);
    if (new Set(vs).size !== vs.length) { toast.error("Deux statuts ont le même identifiant."); return; }
    setSaving(true);
    try {
      await api.put("/sale-statuses", { statuses: clean });
      toast.success("Statuts enregistrés");
      onSaved?.();
      onOpenChange(false);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (detail && typeof detail === "object" && detail.used) {
        toast.error(`Statuts utilisés : ${Object.entries(detail.used).map(([k, n]) => `${k}(${n})`).join(", ")}`);
      } else {
        toast.error(formatApiError(err));
      }
    } finally { setSaving(false); }
  };

  const preview = useMemo(() => rows.filter((r) => r.active !== false), [rows]);

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!saving) onOpenChange(v); }}>
      <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="status-manager-dialog">
        <DialogHeader>
          <DialogTitle>Gérer les statuts de vente</DialogTitle>
          <p className="text-sm text-slate-500">
            Glissez pour réordonner. Cliquez sur la pastille pour changer la couleur. Un statut système peut être désactivé et renommé mais pas supprimé.
          </p>
        </DialogHeader>

        {loading && <div className="p-6 text-center text-slate-500"><Loader2 size={16} className="animate-spin inline mr-2" />Chargement…</div>}

        {!loading && (
          <>
            <div className="space-y-1.5 mt-2" data-testid="status-manager-list">
              {rows.map((r, idx) => (
                <div
                  key={r.value + idx}
                  draggable
                  onDragStart={() => onDragStart(idx)}
                  onDragOver={onDragOver}
                  onDrop={() => onDrop(idx)}
                  className={`flex items-center gap-2 p-2 rounded-md border transition ${dragging === idx ? "opacity-40" : ""} ${r.active === false ? "bg-slate-50 border-slate-200 opacity-70" : "bg-white border-slate-200 hover:border-slate-300"}`}
                  data-testid={`status-row-${r.value}`}
                >
                  <span className="text-slate-400 cursor-grab active:cursor-grabbing" title="Glisser pour déplacer">
                    <GripVertical size={14} />
                  </span>
                  <ColorPicker value={r.color} onChange={(c) => updateRow(idx, { color: c })} />
                  <Input
                    value={r.label}
                    onChange={(e) => updateRow(idx, { label: e.target.value })}
                    className="h-8 flex-1 min-w-0"
                    data-testid={`status-label-${r.value}`}
                  />
                  {r.system ? (
                    <Badge variant="outline" className="text-[10px] shrink-0">Système</Badge>
                  ) : (
                    <span className="text-[10px] text-slate-400 shrink-0">{r.value}</span>
                  )}
                  {(usage[r.value] || 0) > 0 && (
                    <span className="text-[10px] text-slate-500 shrink-0 whitespace-nowrap">{usage[r.value]} vente{usage[r.value] > 1 ? "s" : ""}</span>
                  )}
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      type="button"
                      onClick={() => updateRow(idx, { hides_from_projects: !r.hides_from_projects })}
                      className={`h-8 px-2 rounded-md text-[10px] uppercase tracking-widest transition flex items-center gap-1 ${r.hides_from_projects ? "bg-red-100 text-red-800 border border-red-300" : "text-slate-400 hover:text-slate-800 hover:bg-slate-100 border border-transparent"}`}
                      title={r.hides_from_projects ? "Ce statut masque le chantier de Kanban/Planning — cliquer pour désactiver" : "Cliquer pour que ce statut masque automatiquement le chantier lié"}
                      data-testid={`status-hides-${r.value}`}
                    >
                      <EyeOff size={11} /> {r.hides_from_projects ? "Masque" : "Visible"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setRows((rs) => rs.map((x, i) => ({ ...x, default: i === idx })))}
                      className={`h-8 px-2 rounded-md text-[10px] uppercase tracking-widest transition ${r.default ? "bg-emerald-100 text-emerald-800 border border-emerald-300" : "text-slate-400 hover:text-slate-800 hover:bg-slate-100"}`}
                      title={r.default ? "Statut par défaut" : "Définir comme statut par défaut"}
                      data-testid={`status-default-${r.value}`}
                    >{r.default ? "Défaut ✓" : "Défaut"}</button>
                    <Switch
                      checked={r.active !== false}
                      onCheckedChange={(v) => updateRow(idx, { active: v })}
                      data-testid={`status-active-${r.value}`}
                    />
                    <button
                      type="button"
                      onClick={() => removeRow(idx)}
                      disabled={r.system}
                      className="h-8 w-8 grid place-items-center rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50 disabled:opacity-30 disabled:cursor-not-allowed"
                      title={r.system ? "Statut système (non supprimable)" : (usage[r.value] || 0) > 0 ? `Supprimer (${usage[r.value]} ventes à réaffecter)` : "Supprimer"}
                      data-testid={`status-remove-${r.value}`}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <div className="flex flex-wrap items-center gap-2 mt-3">
              <Button variant="outline" size="sm" onClick={addRow} data-testid="status-add-btn">
                <Plus size={13} className="mr-1" /> Ajouter un statut
              </Button>
              <Button variant="outline" size="sm" onClick={resetDefaults} data-testid="status-reset-btn">
                <RotateCcw size={13} className="mr-1" /> Config QYLOT recommandée
              </Button>
            </div>

            <div className="mt-4 border-t border-slate-200 pt-3">
              <p className="overline mb-2">Aperçu (statuts actifs)</p>
              <div className="flex flex-wrap gap-1.5" data-testid="status-preview">
                {preview.length === 0 && <span className="text-xs text-slate-400 italic">Aucun statut actif</span>}
                {preview.map((r) => (
                  <Badge key={r.value} className={`${clsFromColor(r.color)} border-0`}>{r.label}</Badge>
                ))}
              </div>
            </div>
          </>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>Annuler</Button>
          <Button onClick={save} disabled={saving || loading} data-testid="status-manager-save">
            {saving ? (<><Loader2 size={13} className="mr-1 animate-spin" /> Enregistrement…</>) : (<><Check size={13} className="mr-1" /> Enregistrer</>)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
