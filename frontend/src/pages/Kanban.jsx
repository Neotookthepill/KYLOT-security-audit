import React, { useEffect, useState, useMemo } from "react";
import api, { downloadApiFile, formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Download, Phone, MapPin, Calendar as CalIcon, User, CalendarOff } from "lucide-react";
import { toast } from "sonner";
import ProjectDialog from "@/components/ProjectDialog";
import AbsencesDialog from "@/components/AbsencesDialog";
import useTeam from "@/lib/useTeam";
import { useAuth } from "@/contexts/AuthContext";

const columns = [
  { key: "a_planifier", label: "À planifier", color: "bg-slate-100 text-slate-700" },
  // iter158 : renommage de la colonne "En cours" → "PROG" (demande utilisateur Msg 350).
  { key: "en_cours", label: "PROG", color: "bg-amber-100 text-amber-800" },
  { key: "termine", label: "À encaisser", color: "bg-emerald-100 text-emerald-800" },
];

const priorityColor = {
  basse: "border-l-slate-300",
  moyenne: "border-l-blue-400",
  haute: "border-l-red-500",
};

export default function Kanban() {
  const { user, can, loading: authLoading } = useAuth();
  const { techniciens, sousTraitants } = useTeam();
  // iter140 : les sous-traitants apparaissent dans le planning/kanban admin comme les techniciens.
  //   Un sous-traitant ne peut se connecter que si son compte a un email — mais côté admin,
  //   il est toujours listable pour être assigné à des chantiers (même sans email).
  const assignables = useMemo(() => {
    const seen = new Set();
    const out = [];
    for (const t of techniciens) {
      const k = (t.name || "").trim().toLowerCase();
      if (k && !seen.has(k)) { seen.add(k); out.push({ ...t, _kind: "technicien" }); }
    }
    for (const s of sousTraitants) {
      const k = (s.name || "").trim().toLowerCase();
      if (k && !seen.has(k)) { seen.add(k); out.push({ ...s, _kind: "sous_traitant" }); }
    }
    return out;
  }, [techniciens, sousTraitants]);
  const [projects, setProjects] = useState([]);
  const [absences, setAbsences] = useState([]);
  const [absOpen, setAbsOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [filter, setFilter] = useState("__all");

  const load = async () => {
    try {
      const suffix = filter === "__deleted" ? "?include_deleted=only" : "";
      setProjects((await api.get(`/projects${suffix}`)).data);
    }
    catch (err) { toast.error(formatApiError(err)); }
  };
  const loadAbsences = async () => {
    // iter159 : seuls admin/responsable/super_admin voient les absences (privacy).
    if (!(user?.role === "admin" || user?.role === "responsable" || user?.role === "super_admin")) {
      setAbsences([]);
      return;
    }
    try { setAbsences((await api.get("/absences")).data || []); } catch (_) {}
  };
  useEffect(() => {
    if (authLoading || !user?.id) return;
    load(); loadAbsences();
    const onFocus = () => { load(); loadAbsences(); };
    const onVis = () => { if (document.visibilityState === "visible") onFocus(); };
    // iter52: rafraîchir immédiatement quand une vente change de statut (annule → chantier disparaît)
    const onSalesUpdated = () => { load(); };
    // iter216 : synchronisation temps réel Kanban ↔ Planning — un statut modifié
    // sur le Planning se reflète instantanément dans le Kanban (et inversement).
    const onProjectUpdated = () => { load(); };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("kylot:sales-updated", onSalesUpdated);
    window.addEventListener("kylot:project-updated", onProjectUpdated);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("kylot:sales-updated", onSalesUpdated);
      window.removeEventListener("kylot:project-updated", onProjectUpdated);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, user?.id, filter]);

  // iter87 : suppression manuelle (soft-delete) + restauration d'un chantier supprimé
  const removeProject = async (id, clientName) => {
    if (!window.confirm(`Supprimer le chantier de ${clientName || "ce client"} ?\nIl restera consultable via le filtre « Chantiers supprimés ».`)) return;
    try { await api.delete(`/projects/${id}`); toast.success("Chantier supprimé"); load(); }
    catch (err) { toast.error(formatApiError(err)); }
  };
  const restoreProject = async (id) => {
    try { await api.post(`/projects/${id}/restore`); toast.success("Chantier restauré"); load(); }
    catch (err) { toast.error(formatApiError(err)); }
  };

  const canFilter = user?.role !== "technicien" && user?.role !== "sous_traitant";
  const canEdit = can("projects", "edit");
  // iter157 : un technicien/sous-traitant ne peut ni supprimer ni renvoyer en "À planifier"
  //   — il peut uniquement basculer vers "À encaisser" (fin de son travail) et "Chantier terminé".
  const isTech = user?.role === "technicien" || user?.role === "sous_traitant";
  const canManageAbs = can("planning", "edit", "team");

  const _today = new Date();
  const todayIso = `${_today.getFullYear()}-${String(_today.getMonth() + 1).padStart(2, "0")}-${String(_today.getDate()).padStart(2, "0")}`;
  const activeAbsences = useMemo(
    () => absences.filter((a) => a.date_from <= todayIso && a.date_to >= todayIso),
    [absences, todayIso]
  );

  const visible = useMemo(() => {
    // iter108 : les chantiers "encaisse" (terminés + encaissés) sont masqués du Kanban
    //   mais restent visibles dans le Planning (colonne verte). Sauf en vue "supprimés".
    const base = filter === "__deleted" ? projects : projects.filter((p) => p.status !== "encaisse");
    if (filter === "__all" || filter === "__deleted") return base;
    if (filter === "__none") return base.filter((p) => !p.assigned_to || (Array.isArray(p.assigned_to) && p.assigned_to.length === 0));
    return base.filter((p) => {
      const list = Array.isArray(p.assigned_to) ? p.assigned_to : (p.assigned_to ? [p.assigned_to] : []);
      return list.map((n) => n.toLowerCase()).includes(filter.toLowerCase());
    });
  }, [projects, filter]);

  const move = async (id, newStatus) => {
    try {
      await api.put(`/projects/${id}`, { status: newStatus });
      toast.success("Chantier mis à jour");
      // iter216 : broadcast pour que le Planning se recharge instantanément
      try { window.dispatchEvent(new CustomEvent("kylot:project-updated", { detail: { id, status: newStatus } })); } catch (_) {}
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const onDrop = async (e, status) => {
    e.preventDefault();
    const id = e.dataTransfer.getData("id");
    if (id) move(id, status);
  };

  const exportCsv = async () => {
    await downloadApiFile("/export/projects.csv", "chantiers.csv");
  };

  return (
    <div className="p-4 md:p-8">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-6 flex-wrap gap-3">
        <div>
          <p className="overline">Vue kanban</p>
          <h1 className="font-display text-3xl md:text-4xl font-semibold tracking-tight">Chantiers</h1>
          {(user?.role === "technicien" || user?.role === "sous_traitant") && <p className="text-sm text-slate-500 mt-2">Vous voyez uniquement les chantiers qui vous sont assignés.</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canFilter && user?.role !== "commercial" && (
            <div className="flex items-center gap-2">
              <User size={14} className="text-slate-500" />
              <Select value={filter} onValueChange={setFilter}>
                <SelectTrigger className="h-9 w-52" data-testid="kanban-filter"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all">Tous les techniciens & sous-traitants</SelectItem>
                  <SelectItem value="__none">Non assignés</SelectItem>
                  {assignables.map((t) => (
                    <SelectItem key={t.id} value={t.name}>
                      {t.name}{t._kind === "sous_traitant" ? " · S/T" : ""}
                    </SelectItem>
                  ))}
                  <SelectItem value="__deleted">Chantiers supprimés</SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}
          {canManageAbs && (
            <Button variant="outline" onClick={() => setAbsOpen(true)} data-testid="kanban-manage-absences" className="border-red-200 text-red-700 hover:bg-red-50">
              <CalendarOff size={16} className="mr-2" /> Absences
            </Button>
          )}
          {user?.role === "admin" && (
            <Button variant="outline" onClick={exportCsv} data-testid="export-projects-btn">
              <Download size={16} className="mr-2" /> Exporter CSV
            </Button>
          )}
        </div>
      </div>

      {activeAbsences.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2 items-center bg-red-50 border border-red-200 rounded-lg px-3 py-2" data-testid="kanban-absences-banner">
          <span className="text-xs font-semibold text-red-800 uppercase tracking-wider flex items-center gap-1"><CalendarOff size={13} /> Absents aujourd'hui :</span>
          {activeAbsences.map((a) => (
            <Badge key={a.id} className="bg-red-100 text-red-800 border-0" data-testid={`abs-active-${a.id}`}>
              {a.person_name}{a.reason ? ` · ${a.reason}` : ""}
            </Badge>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {columns.map((col) => {
          const items = visible.filter((p) => p.status === col.key);
          return (
            <div
              key={col.key}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => onDrop(e, col.key)}
              className="bg-white border border-slate-200 rounded-xl p-3 min-h-[70vh]"
              data-testid={`kanban-col-${col.key}`}
            >
              <div className="flex items-center justify-between px-2 py-2">
                <div className="flex items-center gap-2">
                  <Badge className={`${col.color} border-0`}>{col.label}</Badge>
                  <span className="text-xs text-slate-500">{items.length}</span>
                </div>
              </div>
              <div className="space-y-2 mt-2">
                {items.map((p) => (
                  <Card
                    key={p.id}
                    draggable
                    onDragStart={(e) => e.dataTransfer.setData("id", p.id)}
                    onClick={() => setEditing(p)}
                    className={`kanban-card p-4 border-l-4 ${priorityColor[p.priority] || "border-l-slate-300"} border-slate-200 shadow-sm cursor-pointer hover:shadow-md`}
                    data-testid={`kanban-card-${p.id}`}
                  >
                    <div className="font-semibold text-slate-900 break-words">{p.client_name}</div>
                    <div className="text-[13px] text-slate-700 mt-1 space-y-0.5">
                      {p.client_phone && <div className="flex items-start gap-1"><Phone size={12} className="mt-0.5 shrink-0" /> <a href={`tel:${p.client_phone}`} className="break-all">{p.client_phone}</a></div>}
                      {p.client_address && <div className="flex items-start gap-1"><MapPin size={12} className="mt-0.5 shrink-0" /> <span className="break-words">{p.client_address}{p.client_postal_code || p.client_city ? `, ${p.client_postal_code || ""} ${p.client_city || ""}`.trim() : ""}</span></div>}
                    </div>
                    <div className="text-sm text-slate-600 mt-0.5">{p.service}</div>
                    {p.commercial && (
                      <div className="text-[11px] text-indigo-700 mt-1">
                        <span className="uppercase tracking-wider text-[9px] text-slate-500 mr-1">{p.is_de ? "Commerciaux" : "Commercial"} :</span>
                        <span className="font-medium">{p.commercial}{p.is_de && p.commercial_2 ? ` + ${p.commercial_2}` : ""}</span>
                        {p.is_de && <span className="ml-1 px-1 py-0.5 rounded bg-indigo-50 text-indigo-800 border border-indigo-100 text-[9px] font-bold">DE</span>}
                      </div>
                    )}
                    <div className="flex flex-wrap gap-3 mt-2 text-xs text-slate-500">
                      {/* iter197 — Le label « En attente acceptation financement » suit désormais
                          le STATUT de la vente (attente_fi), pas seulement le sentinel scheduled_date.
                          Corrige le bug où Martine LEPESQUEUX affichait « 2026-09-07 » au lieu du label. */}
                      {(p.sale_status === "attente_fi" || p.scheduled_date === "attente_financement") && (
                        <span className="flex items-center gap-1 text-red-600 font-medium"><CalIcon size={11} /> En attente acceptation financement</span>
                      )}
                      {p.scheduled_date === "attente_14j" && p.sale_status !== "attente_fi" && <span className="flex items-center gap-1 text-amber-700 font-medium"><CalIcon size={11} /> En attente délai 14 jours</span>}
                      {p.scheduled_date && !["attente_financement","attente_14j"].includes(p.scheduled_date) && p.sale_status !== "attente_fi" && <span className="flex items-center gap-1"><CalIcon size={11} /> {p.scheduled_date}</span>}
                    </div>
                    {(() => {
                      const list = Array.isArray(p.assigned_to) ? p.assigned_to : (p.assigned_to ? [p.assigned_to] : []);
                      return list.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {list.map((n) => (
                            <Badge key={n} className="bg-slate-100 text-slate-700 border-0"><User size={10} className="mr-1" />{n}</Badge>
                          ))}
                        </div>
                      );
                    })()}
                    <div className="flex gap-1 mt-3 flex-wrap">
                      {filter === "__deleted" ? (
                        <button
                          onClick={(e) => { e.stopPropagation(); restoreProject(p.id); }}
                          className="text-[11px] px-2 py-1 rounded-md border border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                          data-testid={`restore-${p.id}`}
                        >
                          ↺ Restaurer
                        </button>
                      ) : (
                        <>
                          {columns.map((c) => {
                            if (p.status === c.key) return null;
                            // iter162 : les techniciens/sous-traitants n'ont plus AUCUN bouton
                            //   de transition dans le Kanban — ils utilisent uniquement
                            //   « ✓ Chantier terminé » depuis la fiche (ProjectDialog).
                            if (isTech) return null;
                            return (
                              <button
                                key={c.key}
                                onClick={(e) => { e.stopPropagation(); move(p.id, c.key); }}
                                className="text-[11px] px-2 py-1 rounded-md border border-slate-200 text-slate-600 hover:bg-slate-50"
                                data-testid={`move-${p.id}-${c.key}`}
                              >
                                → {c.label}
                              </button>
                            );
                          })}
                          {canEdit && p.status === "termine" && (
                            <button
                              onClick={(e) => { e.stopPropagation(); move(p.id, "encaisse"); }}
                              className="text-[11px] px-2 py-1 rounded-md border border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100 font-semibold"
                              title="Marquer comme encaissé — le chantier disparaît du Kanban mais reste visible dans le planning"
                              data-testid={`finish-${p.id}`}
                            >
                              ✓ Terminé
                            </button>
                          )}
                        </>
                      )}
                      {canEdit && !isTech && filter !== "__deleted" && (
                        <button
                          onClick={(e) => { e.stopPropagation(); removeProject(p.id, p.client_name); }}
                          className="text-[11px] px-2 py-1 rounded-md border border-red-200 text-red-700 hover:bg-red-50 ml-auto"
                          title="Supprimer ce chantier (restaurable via le filtre 'Chantiers supprimés')"
                          data-testid={`delete-${p.id}`}
                        >
                          🗑 Supprimer
                        </button>
                      )}
                    </div>
                  </Card>
                ))}
                {items.length === 0 && (
                  <div className="text-xs text-slate-400 px-2 py-6 text-center">Aucun chantier</div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <ProjectDialog project={editing} onClose={() => setEditing(null)} onSaved={load} />
      <AbsencesDialog open={absOpen} onOpenChange={setAbsOpen} onChanged={loadAbsences} />
    </div>
  );
}
