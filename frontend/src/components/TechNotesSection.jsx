import React, { useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Loader2, StickyNote, Users, Lock } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

/**
 * Per-technician private notes on a chantier.
 * - Admin / Responsable: read+edit every technician's note.
 * - Technicien: read+edit ONLY their own note (backend enforces this too).
 */
export default function TechNotesSection({ projectId, assignedList }) {
  const { user } = useAuth();
  const role = user?.role;
  const canManageAll = role === "admin" || role === "responsable" || role === "super_admin";
  const isTech = role === "technicien";
  const myName = user?.name || "";
  const normalize = (s) => (s || "").trim().toLowerCase();

  // iter155 : matching robuste (accents/casse + tokens sur espace|_|-|. + prefix)
  const stripAccents = (s) => (s || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "");
  const norm = (s) => stripAccents((s || "").trim().toLowerCase());
  const toks = (s) => norm(s).split(/[\s_\-\.]+/).filter(Boolean);
  const fuzzyEq = (a, b) => {
    const na = norm(a), nb = norm(b);
    if (!na || !nb) return false;
    if (na === nb) return true;
    if (na.length >= 3 && nb.length >= 3 && (na.startsWith(nb) || nb.startsWith(na))) return true;
    const ta = new Set(toks(a)), tb = new Set(toks(b));
    for (const t of ta) if (tb.has(t)) return true;
    return false;
  };

  const [notes, setNotes] = useState([]); // [{technician_name, note, updated_at}]
  const [loading, setLoading] = useState(false);
  const [drafts, setDrafts] = useState({}); // key -> string
  const [saving, setSaving] = useState({}); // key -> bool

  const load = async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/projects/${projectId}/notes`);
      setNotes(data || []);
      const d = {};
      for (const n of data || []) d[normalize(n.technician_name)] = n.note || "";
      setDrafts(d);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [projectId]);

  // Who's visible for editing?
  const editableTechs = useMemo(() => {
    if (canManageAll) return assignedList || [];
    if (isTech) return (assignedList || []).filter((n) => fuzzyEq(n, myName));
    return [];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canManageAll, isTech, assignedList, myName]);

  const save = async (techName) => {
    const key = normalize(techName);
    const val = drafts[key] ?? "";
    setSaving((s) => ({ ...s, [key]: true }));
    try {
      await api.put(`/projects/${projectId}/notes/${encodeURIComponent(techName)}`, { note: val });
      toast.success("Note enregistrée");
      load();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setSaving((s) => ({ ...s, [key]: false })); }
  };

  if (!projectId) return null;
  if (!canManageAll && !isTech) return null;

  return (
    <div className="rounded-lg border border-indigo-100 bg-indigo-50/30 p-3 space-y-3" data-testid="tech-notes-section">
      <div className="flex items-center gap-2 text-sm font-semibold text-indigo-900">
        <StickyNote size={14} />
        {canManageAll ? "Notes individuelles par technicien" : "Votre note (privée)"}
        {!canManageAll && <Lock size={11} className="text-indigo-500" />}
      </div>
      {canManageAll && (
        <p className="text-[11px] text-indigo-800/80 flex items-center gap-1">
          <Users size={11} /> Chaque note n'est visible que par le technicien concerné, l'admin et le responsable.
        </p>
      )}
      {loading && <div className="flex items-center gap-2 text-xs text-slate-500"><Loader2 size={12} className="animate-spin" /> Chargement…</div>}
      {!loading && editableTechs.length === 0 && (
        <p className="text-xs text-slate-500 italic">Aucun technicien assigné — assignez d'abord des techniciens pour leur laisser des notes.</p>
      )}
      {editableTechs.map((name) => {
        const key = normalize(name);
        const draft = drafts[key] ?? "";
        const existing = notes.find((n) => normalize(n.technician_name) === key);
        const isSaving = !!saving[key];
        return (
          <div key={key} className="rounded-md bg-white border border-indigo-100 p-2.5 space-y-1.5" data-testid={`tech-note-block-${key}`}>
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-slate-800">{name}</span>
              {existing?.updated_at && (
                <span className="text-[10px] text-slate-400">MàJ {new Date(existing.updated_at).toLocaleDateString("fr-FR")}</span>
              )}
            </div>
            <Textarea
              rows={3}
              value={draft}
              onChange={(e) => setDrafts((d) => ({ ...d, [key]: e.target.value }))}
              placeholder={`Note privée pour ${name}…`}
              data-testid={`tech-note-input-${key}`}
              className="text-sm"
            />
            <div className="flex justify-end">
              <Button size="sm" onClick={() => save(name)} disabled={isSaving || draft === (existing?.note || "")} data-testid={`tech-note-save-${key}`}>
                {isSaving ? <Loader2 size={12} className="animate-spin mr-1" /> : null}
                Enregistrer
              </Button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
