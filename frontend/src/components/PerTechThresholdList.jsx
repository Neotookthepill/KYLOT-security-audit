import React, { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { RotateCcw, Check } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";

/**
 * iter116 : liste des techniciens (avec `overtime_enabled`) et leur seuil d'alerte
 * heures sup personnalisé. Vide = fallback sur le seuil global.
 * Modifications sauvegardées à la volée via PUT /api/team/{id}.
 */
export default function PerTechThresholdList({ globalThreshold }) {
  const [techs, setTechs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState({}); // id -> bool
  const [dirty, setDirty] = useState({}); // id -> string (raw input)

  const load = async () => {
    try {
      setLoading(true);
      const { data } = await api.get("/team?type=technicien");
      setTechs(Array.isArray(data) ? data : []);
    } catch (_) {
      setTechs([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const commit = async (t, rawValue) => {
    setSaving((prev) => ({ ...prev, [t.id]: true }));
    try {
      const trimmed = (rawValue ?? "").toString().trim();
      const payload = { overtime_alert_threshold: trimmed === "" ? null : parseFloat(trimmed) };
      await api.put(`/team/${t.id}`, payload);
      setTechs((prev) => prev.map((x) => x.id === t.id ? { ...x, overtime_alert_threshold: payload.overtime_alert_threshold } : x));
      setDirty((prev) => { const n = { ...prev }; delete n[t.id]; return n; });
      toast.success(`Seuil de ${t.name} mis à jour`);
    } catch (e) {
      toast.error(formatApiError(e));
    } finally {
      setSaving((prev) => { const n = { ...prev }; delete n[t.id]; return n; });
    }
  };

  const reset = async (t) => commit(t, "");

  if (loading) return <p className="text-xs text-slate-400">Chargement…</p>;
  if (!techs.length) return <p className="text-xs text-slate-400">Aucun technicien enregistré.</p>;

  return (
    <div className="space-y-2" data-testid="per-tech-threshold-list">
      {techs.map((t) => {
        const current = t.id in dirty ? dirty[t.id] : (t.overtime_alert_threshold ?? "");
        const usingGlobal = current === "" || current === null || current === undefined;
        const effective = usingGlobal ? (parseFloat(globalThreshold) || 30) : parseFloat(current);
        return (
          <div key={t.id} className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white p-2.5" data-testid={`tech-threshold-row-${t.id}`}>
            <span className="flex-1 text-sm font-medium text-slate-800 truncate">{t.name}</span>
            <Input
              type="number"
              min="0"
              step="1"
              placeholder={`Global (${parseFloat(globalThreshold) || 30})`}
              value={current === null || current === undefined ? "" : current}
              onChange={(e) => setDirty((prev) => ({ ...prev, [t.id]: e.target.value }))}
              className="h-8 w-28 text-center font-mono text-sm"
              data-testid={`tech-threshold-input-${t.id}`}
            />
            <span className="text-xs text-slate-500 w-24 tabular-nums">
              → {effective} h/mois {usingGlobal && <em className="text-slate-400">(global)</em>}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={!(t.id in dirty) || !!saving[t.id]}
              onClick={() => commit(t, current)}
              className="h-8"
              data-testid={`tech-threshold-save-${t.id}`}
              title="Enregistrer ce seuil"
            >
              <Check size={13} />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={usingGlobal || !!saving[t.id]}
              onClick={() => reset(t)}
              className="h-8"
              data-testid={`tech-threshold-reset-${t.id}`}
              title="Revenir au seuil global"
            >
              <RotateCcw size={13} />
            </Button>
          </div>
        );
      })}
    </div>
  );
}
