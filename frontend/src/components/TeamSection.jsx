import React, { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { X, Plus, Users2, Hammer, Check, Pencil, Mail, MailX, Eye, EyeOff, Clock, Building2 } from "lucide-react";
import { toast } from "sonner";
import useTeam from "@/lib/useTeam";

const fmtEur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);

// iter68 : libellés utilisés par les toggles de visibilité société
const LABELS = {
  see_company_ca: "Voir CA société",
  see_company_objectif: "Voir objectif société",
  see_company_progress: "Voir % objectif société",
  // iter151 (v2) : apparaître dans le widget "Classement commercial" du Tableau de bord.
  // Stocké dans le champ existant `hidden_from_ranking` (inversé : hidden=true → NON).
  hidden_from_ranking: "Apparaître dans le classement commercial",
};

function CommercialList({ members, onChanged }) {
  const [adding, setAdding] = useState("");
  const [addingEmail, setAddingEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null); // {id, objectif, email}
  // iter192 — Suggestions d'utilisateurs existants pour éviter les doublons commerciaux
  // (ex : « Kelian » alors que « Kelyan Richard » est déjà un compte commercial).
  const [userComs, setUserComs] = useState([]);
  React.useEffect(() => {
    api.get("/users").then((r) => {
      const list = Array.isArray(r.data) ? r.data : (r.data?.items || []);
      setUserComs(list.filter((u) => ["commercial", "responsable", "admin"].includes(u.role)));
    }).catch(() => {});
  }, []);
  const norm = (s) => (s || "").toString().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
  const suggestions = React.useMemo(() => {
    const q = norm(adding);
    if (!q) return [];
    const memberNorms = new Set((members || []).map((m) => norm(m.name)));
    return userComs.filter((u) => {
      const un = norm(u.name);
      if (memberNorms.has(un)) return false;
      return un.startsWith(q) || un.split(" ")[0].startsWith(q);
    }).slice(0, 4);
  }, [adding, userComs, members]);

  const add = async () => {
    const name = adding.trim();
    if (!name) return;
    setBusy(true);
    try {
      await api.post("/team", { name, type: "commercial", email: addingEmail.trim() });
      toast.success(`${name} ajouté`);
      setAdding("");
      setAddingEmail("");
      onChanged();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  const remove = async (m) => {
    if (!window.confirm(`Supprimer ${m.name} ?`)) return;
    try { await api.delete(`/team/${m.id}`); toast.success(`${m.name} retiré`); onChanged(); }
    catch (err) { toast.error(formatApiError(err)); }
  };

  const saveEdit = async () => {
    try {
      await api.put(`/team/${editing.id}`, { objectif: parseFloat(editing.objectif || 0), email: editing.email || "" });
      toast.success("Enregistré");
      setEditing(null);
      onChanged();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  // iter61 : toggle visibilité classement pour un commercial (admin uniquement)
  const toggleHidden = async (m) => {
    const next = !m.hidden_from_ranking;
    try {
      await api.put(`/team/${m.id}`, { hidden_from_ranking: next });
      toast.success(next ? `${m.name} masqué du classement public` : `${m.name} de nouveau visible dans le classement`);
      onChanged();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  // iter68 : toggle visibilité société (par flag). iter151 : gère aussi `hidden_from_ranking`
  //   qui est INVERSÉ sémantiquement (hidden=true → affichage "NON").
  const toggleCompanyFlag = async (m, field) => {
    if (field === "hidden_from_ranking") {
      // Le toggle affiche "OUI" quand hidden=false. Basculer inverse.
      const currentHidden = !!m.hidden_from_ranking;
      try {
        await api.put(`/team/${m.id}`, { hidden_from_ranking: !currentHidden });
        toast.success(currentHidden ? `Activé : ${LABELS.hidden_from_ranking}` : `Désactivé : ${LABELS.hidden_from_ranking}`);
        onChanged();
      } catch (err) { toast.error(formatApiError(err)); }
      return;
    }
    const cur = m[field] !== false;
    try {
      await api.put(`/team/${m.id}`, { [field]: !cur });
      toast.success(!cur ? `Activé : ${LABELS[field]}` : `Désactivé : ${LABELS[field]}`);
      onChanged();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  // iter68/151 : master toggle — les 3 flags société + `hidden_from_ranking` (inversé)
  const toggleAllCompanyFlags = async (m, next) => {
    try {
      await api.put(`/team/${m.id}`, {
        see_company_ca: next,
        see_company_objectif: next,
        see_company_progress: next,
        hidden_from_ranking: !next, // inversé : "tout activer" = hidden=false
      });
      toast.success(next ? `${m.name} : visibilité société activée (4 champs)` : `${m.name} : visibilité société désactivée`);
      onChanged();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const [expandedId, setExpandedId] = useState(null);
  const [showRecap, setShowRecap] = useState(false);

  // iter70/90 : compter globalement les visibilités actives sur les commerciaux — guard contre members non-array
  const safeMembers = Array.isArray(members) ? members.filter((m) => m && m.id) : [];
  const recapStats = safeMembers.reduce((acc, m) => {
    acc.ca += m.see_company_ca !== false ? 1 : 0;
    acc.objectif += m.see_company_objectif !== false ? 1 : 0;
    acc.progress += m.see_company_progress !== false ? 1 : 0;
    acc.ranking += m.hidden_from_ranking ? 0 : 1;
    return acc;
  }, { ca: 0, objectif: 0, progress: 0, ranking: 0 });

  return (
    <Card className="border-slate-200 shadow-sm">
      <div className="p-4 border-b border-slate-200 flex items-center gap-2">
        <Users2 size={16} className="text-slate-500" />
        <p className="font-display text-lg font-semibold">Commerciaux</p>
        <Badge className="bg-slate-100 text-slate-700 border-0 ml-auto">{safeMembers.length}</Badge>
        <button
          type="button"
          onClick={() => setShowRecap((v) => !v)}
          className={`text-[10px] px-2 py-0.5 rounded border transition ${showRecap ? "border-indigo-300 bg-indigo-50 text-indigo-700" : "border-slate-200 text-slate-500 hover:bg-slate-50"}`}
          title="Vue récapitulative de toutes les visibilités société"
          data-testid="team-recap-toggle"
        >
          Récap visibilités
        </button>
      </div>
      {showRecap && safeMembers.length > 0 && (
        <div className="p-3 border-b border-slate-200 bg-slate-50/60" data-testid="team-recap-panel">
          <div className="text-[10px] uppercase tracking-widest font-semibold text-slate-500 mb-2 flex items-center gap-2">
            Visibilités par commercial
            <span className="ml-auto text-slate-400 font-normal normal-case tracking-normal">CA société {recapStats.ca}/{safeMembers.length} · Objectif {recapStats.objectif}/{safeMembers.length} · % {recapStats.progress}/{safeMembers.length} · Classement {recapStats.ranking}/{safeMembers.length}</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="py-1.5 pr-2 font-medium">Commercial</th>
                  <th className="py-1.5 px-2 font-medium text-center">CA société</th>
                  <th className="py-1.5 px-2 font-medium text-center">Objectif société</th>
                  <th className="py-1.5 px-2 font-medium text-center">% société</th>
                  <th className="py-1.5 px-2 font-medium text-center">Classement public</th>
                </tr>
              </thead>
              <tbody>
                {safeMembers.map((m) => {
                  const cells = [
                    { key: "see_company_ca", val: m.see_company_ca !== false },
                    { key: "see_company_objectif", val: m.see_company_objectif !== false },
                    { key: "see_company_progress", val: m.see_company_progress !== false },
                    { key: "ranking", val: !m.hidden_from_ranking },
                  ];
                  return (
                    <tr key={m.id} className="border-b border-slate-100 last:border-0 hover:bg-white transition" data-testid={`team-recap-row-${m.id}`}>
                      <td className="py-1.5 pr-2 font-medium text-slate-800 truncate max-w-[140px]">{m.name}</td>
                      {cells.map((c) => (
                        <td key={c.key} className="py-1.5 px-2 text-center">
                          <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold ${c.val ? "bg-emerald-100 text-emerald-700" : "bg-slate-200 text-slate-500"}`}>
                            {c.val ? <Eye size={9} /> : <EyeOff size={9} />}
                            {c.val ? "Oui" : "Non"}
                          </span>
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-[10px] text-slate-500 mt-2">Cliquez sur l'icône <Building2 size={9} className="inline" /> ou <Eye size={9} className="inline" /> à côté d'un commercial pour ajuster individuellement.</p>
        </div>
      )}
      <div className="p-4">
        <div className="space-y-1.5 max-h-[320px] overflow-y-auto">
          {(!Array.isArray(members) || members.length === 0) && <p className="text-sm text-slate-500">Aucun membre.</p>}
          {(Array.isArray(members) ? members : []).filter((m) => m && m.id).map((m) => (
            <div key={m.id} className="flex flex-col gap-1 px-2 py-2 rounded-md border border-slate-100 hover:bg-slate-50" data-testid={`team-commercial-${m.id}`}>
              {editing?.id === m.id ? (
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm flex-1">{m.name}</span>
                    <Button size="sm" onClick={saveEdit} data-testid={`team-obj-save-${m.id}`} className="h-7 px-2"><Check size={12} /></Button>
                    <button onClick={() => setEditing(null)} className="text-slate-400 hover:text-slate-700" aria-label="Annuler"><X size={14} /></button>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <Input type="number" value={editing.objectif} onChange={(e) => setEditing({ ...editing, objectif: e.target.value })} className="h-7 text-xs" placeholder="Objectif €" data-testid={`team-obj-input-${m.id}`} />
                    <Input type="email" value={editing.email} onChange={(e) => setEditing({ ...editing, email: e.target.value })} className="h-7 text-xs" placeholder="email@domaine.fr" data-testid={`team-email-input-${m.id}`} />
                  </div>
                </div>
              ) : (
                <>
                <div className="flex items-center gap-2">
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm">{m.name}</div>
                    <div className="text-[11px] text-slate-500 flex items-center gap-1.5 mt-0.5 truncate">
                      {m.email ? (
                        <span className="flex items-center gap-1"><Mail size={10} className="shrink-0" /><span className="truncate">{m.email}</span></span>
                      ) : (
                        <span className="text-amber-600 flex items-center gap-1" title="Sans email, ce commercial ne recevra pas les rappels J-1"><MailX size={10} className="shrink-0" />Pas d'email</span>
                      )}
                    </div>
                  </div>
                  <span className="text-xs text-slate-500 min-w-[80px] text-right">Objectif : <span className="font-semibold text-slate-700">{m.objectif > 0 ? fmtEur(m.objectif) : "—"}</span></span>
                  <button
                    onClick={() => setExpandedId(expandedId === m.id ? null : m.id)}
                    className={`shrink-0 ${expandedId === m.id ? "text-indigo-600" : "text-slate-400 hover:text-slate-700"}`}
                    title="Visibilité société (CA / Objectif / %)"
                    aria-label="Réglages visibilité société"
                    data-testid={`team-company-toggle-${m.id}`}
                  >
                    <Building2 size={13} />
                  </button>
                  <button
                    onClick={() => toggleHidden(m)}
                    className={`shrink-0 ${m.hidden_from_ranking ? "text-amber-600 hover:text-amber-800" : "text-slate-400 hover:text-slate-700"}`}
                    title={m.hidden_from_ranking ? "Masqué du classement public — cliquez pour rendre visible" : "Visible dans le classement — cliquez pour masquer aux autres"}
                    aria-label={m.hidden_from_ranking ? "Rendre visible" : "Masquer du classement"}
                    data-testid={`team-visibility-${m.id}`}
                  >
                    {m.hidden_from_ranking ? <EyeOff size={13} /> : <Eye size={13} />}
                  </button>
                  <button onClick={() => setEditing({ id: m.id, objectif: m.objectif || 0, email: m.email || "" })} className="text-slate-400 hover:text-slate-700" data-testid={`team-obj-edit-${m.id}`} aria-label="Modifier"><Pencil size={12} /></button>
                  <button onClick={() => remove(m)} className="text-slate-400 hover:text-red-600" data-testid={`team-commercial-${m.id}-remove`} aria-label={`Supprimer ${m.name}`}><X size={14} /></button>
                </div>
                {expandedId === m.id && (
                  <div className="mt-1 pt-2 border-t border-slate-100 space-y-1.5" data-testid={`team-company-panel-${m.id}`}>
                    <div className="flex items-center gap-2">
                      <p className="text-[11px] uppercase font-semibold text-slate-500 tracking-wider flex-1">Visibilité société pour ce commercial</p>
                      {(() => {
                        // iter150/151 : "Tout activer" et "Tout désactiver" reflètent l'état
                        // réel des 4 flags (3 see_company_* + hidden_from_ranking inversé).
                        const rankVisible = !m.hidden_from_ranking;
                        const allOn = m.see_company_ca !== false && m.see_company_objectif !== false && m.see_company_progress !== false && rankVisible;
                        const allOff = m.see_company_ca === false && m.see_company_objectif === false && m.see_company_progress === false && !rankVisible;
                        return (
                          <>
                            <button
                              type="button"
                              onClick={() => toggleAllCompanyFlags(m, true)}
                              disabled={allOn}
                              className={`text-[10px] px-2 py-0.5 rounded border transition ${allOn ? "border-slate-200 bg-slate-50 text-slate-400 cursor-default" : "border-emerald-200 text-emerald-700 hover:bg-emerald-50"}`}
                              data-testid={`team-company-all-on-${m.id}`}
                            >Tout activer</button>
                            <button
                              type="button"
                              onClick={() => toggleAllCompanyFlags(m, false)}
                              disabled={allOff}
                              className={`text-[10px] px-2 py-0.5 rounded border transition ${allOff ? "border-slate-300 bg-slate-100 text-slate-500 cursor-default" : "border-slate-200 text-slate-600 hover:bg-slate-50"}`}
                              data-testid={`team-company-all-off-${m.id}`}
                            >Tout désactiver</button>
                          </>
                        );
                      })()}
                    </div>
                    {["see_company_ca", "see_company_objectif", "see_company_progress", "hidden_from_ranking"].map((f) => {
                      // iter151 : hidden_from_ranking est INVERSÉ (hidden=true → affiche NON)
                      const enabled = f === "hidden_from_ranking" ? !m.hidden_from_ranking : (m[f] !== false);
                      return (
                        <button
                          key={f}
                          type="button"
                          onClick={() => toggleCompanyFlag(m, f)}
                          className={`w-full flex items-center justify-between text-xs px-2 py-1.5 rounded border transition ${enabled ? "border-emerald-200 bg-emerald-50/50 text-slate-700" : "border-slate-200 bg-white text-slate-500"}`}
                          data-testid={`team-company-flag-${f}-${m.id}`}
                        >
                          <span className="flex items-center gap-2">
                            {enabled ? <Eye size={11} className="text-emerald-600" /> : <EyeOff size={11} className="text-slate-400" />}
                            {LABELS[f]}
                          </span>
                          <span className={`text-[10px] font-semibold ${enabled ? "text-emerald-700" : "text-slate-400"}`}>{enabled ? "OUI" : "NON"}</span>
                        </button>
                      );
                    })}
                    <p className="text-[10px] text-slate-500">Ce commercial verra son CA / Objectif / % personnels dans tous les cas. Ces réglages contrôlent uniquement l'affichage secondaire du périmètre société.</p>
                  </div>
                )}
                </>
              )}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-[1fr_1fr_auto] gap-2 mt-3">
          <Input value={adding} onChange={(e) => setAdding(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} placeholder="Nom du commercial" data-testid="team-commercial-input" />
          <Input type="email" value={addingEmail} onChange={(e) => setAddingEmail(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} placeholder="Email (optionnel)" data-testid="team-commercial-email-input" />
          <Button onClick={add} disabled={busy || !adding.trim()} data-testid="team-commercial-add-btn">
            <Plus size={14} className="mr-1" /> Ajouter
          </Button>
        </div>
        <p className="text-[11px] text-slate-500 mt-2">L'email est utilisé pour envoyer le rappel J-1 des chantiers à 20h la veille.</p>
      </div>
    </Card>
  );
}

function TechnicienList({ members, onChanged }) {
  const [adding, setAdding] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null); // {id, name}
  // iter189 — Suggestions d'utilisateurs déjà existants pour éviter les doublons
  // (ex : "Sébastien" tapé alors que "Sebastien Hurtel" est déjà un compte technicien).
  const [userTechs, setUserTechs] = useState([]);
  React.useEffect(() => {
    api.get("/users").then((r) => {
      const list = Array.isArray(r.data) ? r.data : (r.data?.items || []);
      setUserTechs(list.filter((u) => ["technicien", "sous_traitant"].includes(u.role)));
    }).catch(() => {});
  }, []);
  const norm = (s) => (s || "").toString().normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
  const suggestions = React.useMemo(() => {
    const q = norm(adding);
    if (!q) return [];
    const memberNorms = new Set((members || []).map((m) => norm(m.name)));
    return userTechs.filter((u) => {
      const un = norm(u.name);
      if (memberNorms.has(un)) return false; // déjà présent
      return un.startsWith(q) || un.split(" ")[0].startsWith(q);
    }).slice(0, 4);
  }, [adding, userTechs, members]);

  const add = async () => {
    const name = adding.trim();
    if (!name) return;
    setBusy(true);
    try {
      await api.post("/team", { name, type: "technicien" });
      toast.success(`${name} ajouté`);
      setAdding("");
      onChanged();
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setBusy(false); }
  };

  const remove = async (m) => {
    if (!window.confirm(`Supprimer ${m.name} ?`)) return;
    try { await api.delete(`/team/${m.id}`); toast.success(`${m.name} retiré`); onChanged(); }
    catch (err) { toast.error(formatApiError(err)); }
  };

  const saveName = async () => {
    if (!editing.name.trim()) return toast.error("Nom vide");
    try {
      await api.put(`/team/${editing.id}`, { name: editing.name.trim() });
      toast.success("Nom modifié");
      setEditing(null);
      onChanged();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  // iter62/96 : toggle "autorisé aux heures sup" (indépendant du rôle Technicien pour ne pas
  // affecter les sous-traitants). Persisté sur team_members.overtime_enabled.
  // iter96 : dispatch kylot:team-updated → AuthContext refresh /auth/me instantanément
  //   pour que le menu Heures sup apparaisse/disparaisse sans attendre 20s.
  const toggleOvertime = async (m) => {
    const next = !m.overtime_enabled;
    try {
      await api.put(`/team/${m.id}`, { overtime_enabled: next });
      toast.success(next ? `${m.name} autorisé aux heures sup` : `${m.name} retiré des heures sup`);
      onChanged();
      window.dispatchEvent(new CustomEvent("kylot:team-updated"));
    } catch (err) { toast.error(formatApiError(err)); }
  };

  return (
    <Card className="border-slate-200 shadow-sm">
      <div className="p-4 border-b border-slate-200 flex items-center gap-2">
        <Hammer size={16} className="text-slate-500" />
        <p className="font-display text-lg font-semibold">Techniciens (chantiers & planning)</p>
        <Badge className="bg-slate-100 text-slate-700 border-0 ml-auto">{(Array.isArray(members) ? members : []).length}</Badge>
      </div>
      <div className="p-4">
        <div className="space-y-1.5 max-h-[280px] overflow-y-auto">
          {(!Array.isArray(members) || members.length === 0) && <p className="text-sm text-slate-500">Aucun membre.</p>}
          {(Array.isArray(members) ? members : []).filter((m) => m && m.id).map((m) => (
            <div key={m.id} className="flex items-center gap-2 px-2 py-1.5 rounded-md border border-slate-100 hover:bg-slate-50" data-testid={`team-technicien-${m.id}`}>
              {editing?.id === m.id ? (
                <>
                  <Input value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })} className="h-7 flex-1 text-sm" data-testid={`team-tech-input-${m.id}`} />
                  <Button size="sm" onClick={saveName} data-testid={`team-tech-save-${m.id}`} className="h-7 px-2"><Check size={12} /></Button>
                </>
              ) : (
                <>
                  <span className="font-medium text-sm flex-1">{m.name}</span>
                  <button
                    onClick={() => toggleOvertime(m)}
                    className={`shrink-0 ${m.overtime_enabled ? "text-emerald-600 hover:text-emerald-800" : "text-slate-300 hover:text-slate-500"}`}
                    title={m.overtime_enabled ? "Autorisé aux heures sup — cliquez pour retirer" : "Non autorisé aux heures sup — cliquez pour autoriser"}
                    aria-label={m.overtime_enabled ? "Retirer des heures sup" : "Autoriser heures sup"}
                    data-testid={`team-overtime-${m.id}`}
                  >
                    <Clock size={13} />
                  </button>
                  <button onClick={() => setEditing({ id: m.id, name: m.name })} className="text-slate-400 hover:text-slate-700" data-testid={`team-tech-edit-${m.id}`} aria-label="Renommer"><Pencil size={12} /></button>
                </>
              )}
              <button onClick={() => remove(m)} className="text-slate-400 hover:text-red-600" data-testid={`team-technicien-${m.id}-remove`} aria-label={`Supprimer ${m.name}`}><X size={14} /></button>
            </div>
          ))}
        </div>
        <div className="flex gap-2 mt-3">
          <Input value={adding} onChange={(e) => setAdding(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} placeholder="Ajouter un technicien…" data-testid="team-technicien-input" />
          <Button onClick={() => add()} disabled={busy || !adding.trim()} data-testid="team-technicien-add-btn">
            <Plus size={14} className="mr-1" /> Ajouter
          </Button>
        </div>
        {suggestions.length > 0 && (
          <div className="mt-2 rounded-md border border-indigo-200 bg-indigo-50/50 p-2" data-testid="team-tech-suggestions">
            <p className="text-[11px] text-indigo-800 mb-1.5 font-medium">Ces utilisateurs existent déjà — sélectionne pour éviter un doublon :</p>
            <div className="flex flex-wrap gap-1.5">
              {suggestions.map((u) => (
                <button
                  key={u.id}
                  type="button"
                  onClick={() => { setAdding(u.name); toast.success(`« ${u.name} » sera lié automatiquement (pas de doublon).`); }}
                  className="text-[11px] px-2 py-1 rounded-full bg-white border border-indigo-200 text-indigo-800 hover:bg-indigo-100"
                  data-testid={`team-tech-suggest-${u.id}`}
                >
                  {u.name}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

export default function TeamSection() {
  const { commerciaux, techniciens, sousTraitants, reload } = useTeam();
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mt-6">
      <CommercialList members={commerciaux} onChanged={reload} />
      <TechnicienList members={techniciens} onChanged={reload} />
      <SousTraitantList members={sousTraitants} onChanged={reload} />
    </div>
  );
}

// Génère un mot de passe temporaire lisible (8 caractères, sans ambiguïtés)
function genPassword() {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789";
  let s = "";
  for (let i = 0; i < 8; i++) s += chars[Math.floor(Math.random() * chars.length)];
  return s;
}

// iter92/97 : liste des utilisateurs "sous-traitant" avec ajout direct depuis le bloc
//   - même design/interaction que CommercialList & TechnicienList
//   - "Ajouter" : nom + email → si email existe → promotion (rôle sous_traitant), sinon création
//   - mot de passe temporaire auto-généré en interne, affiché seulement après création
//   - "X" retire le rôle (bascule vers technicien par défaut) — le compte n'est PAS supprimé
function SousTraitantList({ members, onChanged }) {
  const [adding, setAdding] = useState("");
  const [addingEmail, setAddingEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [lastCreated, setLastCreated] = useState(null); // {email, password}

  const notify = () => window.dispatchEvent(new CustomEvent("kylot:team-updated"));

  const add = async () => {
    const name = adding.trim();
    const email = (addingEmail || "").trim().toLowerCase();
    if (!name) { toast.error("Nom requis"); return; }
    setBusy(true);
    try {
      // iter135 : email désormais optionnel (comme les techniciens)
      if (!email) {
        // Pas d'email → crée uniquement le team_member (pas de compte user)
        await api.post("/team", { name, type: "sous_traitant" });
        toast.success(`${name} ajouté comme sous-traitant (sans compte)`);
      } else {
        const usersRes = await api.get("/users");
        const usersList = Array.isArray(usersRes.data) ? usersRes.data : [];
        const existing = usersList.find((u) => (u.email || "").toLowerCase() === email);
        if (existing) {
          if (existing.role === "sous_traitant") {
            toast.info(`${existing.name || email} est déjà sous-traitant`);
          } else {
            await api.put(`/users/${existing.id}`, { role: "sous_traitant" });
            toast.success(`${existing.name || email} rattaché au rôle Sous-traitant`);
          }
        } else {
          const password = genPassword();
          await api.post("/users", { name, email, password, role: "sous_traitant" });
          setLastCreated({ email, password });
          toast.success(`${name} ajouté comme sous-traitant`);
        }
      }
      setAdding("");
      setAddingEmail("");
      onChanged?.();
      notify();
    } catch (err) {
      toast.error(formatApiError(err));
    } finally { setBusy(false); }
  };

  // iter135 : "X" retire le sous-traitant. Si c'est un team_member (sans compte),
  // on DELETE /team/{id}. Sinon (compte user), on bascule le rôle vers technicien (comportement d'origine).
  const removeRole = async (m) => {
    if (m._account_less) {
      if (!window.confirm(`Supprimer ${m.name} de la liste des sous-traitants ?`)) return;
      try {
        await api.delete(`/team/${m.id}`);
        toast.success(`${m.name} supprimé`);
        onChanged?.();
        notify();
      } catch (err) { toast.error(formatApiError(err)); }
      return;
    }
    if (!window.confirm(`Retirer le rôle Sous-traitant de ${m.name} ?\nLe compte est conservé (rôle basculé sur Technicien). Modifiable ensuite dans la table Utilisateurs.`)) return;
    try {
      await api.put(`/users/${m.id}`, { role: "technicien" });
      toast.success(`${m.name} retiré du bloc Sous-traitants`);
      onChanged?.();
      notify();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const safeMembers = (Array.isArray(members) ? members : []).filter((m) => m && m.id);

  return (
    <Card className="border-slate-200 shadow-sm" data-testid="team-sous-traitants">
      <div className="p-4 border-b border-slate-200 flex items-center gap-2">
        <Hammer size={16} className="text-teal-600" />
        <p className="font-display text-lg font-semibold">Sous-traitants</p>
        <Badge className="bg-teal-100 text-teal-800 border-0 ml-auto">{safeMembers.length}</Badge>
      </div>
      <div className="p-4">
        <div className="space-y-1.5 max-h-[280px] overflow-y-auto">
          {safeMembers.length === 0 && <p className="text-sm text-slate-500">Aucun sous-traitant.</p>}
          {safeMembers.map((m) => (
            <div key={m.id} className="flex items-center gap-2 px-2 py-1.5 rounded-md border border-slate-100 hover:bg-slate-50" data-testid={`sous-traitant-${m.id}`}>
              <div className="flex-1 min-w-0">
                <div className="font-medium text-sm truncate">{m.name || "(sans nom)"}</div>
                {m.email && (
                  <div className="text-[11px] text-slate-500 flex items-center gap-1 mt-0.5 truncate">
                    <Mail size={10} className="shrink-0" />
                    <span className="truncate">{m.email}</span>
                  </div>
                )}
              </div>
              <Badge className="bg-teal-50 text-teal-700 border-0 text-[10px] shrink-0">Sous-traitant</Badge>
              <button onClick={() => removeRole(m)} className="text-slate-400 hover:text-red-600 shrink-0" aria-label={`Retirer ${m.name}`} title="Retirer le rôle Sous-traitant (le compte est conservé)" data-testid={`sous-traitant-${m.id}-remove`}><X size={14} /></button>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-[1fr_1fr_auto] gap-2 mt-3">
          <Input value={adding} onChange={(e) => setAdding(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} placeholder="Ajouter un sous-traitant…" data-testid="team-sous-traitant-input" />
          <Input type="email" value={addingEmail} onChange={(e) => setAddingEmail(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} placeholder="Email" data-testid="team-sous-traitant-email-input" />
          <Button onClick={add} disabled={busy || !adding.trim()} data-testid="team-sous-traitant-add-btn">
            <Plus size={14} className="mr-1" /> Ajouter
          </Button>
        </div>
        <p className="text-[11px] text-slate-500 mt-2">
          Si l'email existe déjà dans votre société, le compte est simplement <strong>rattaché</strong> au rôle Sous-traitant (aucun doublon). Sinon un nouveau compte est créé automatiquement avec un mot de passe temporaire affiché après création.
        </p>
        {lastCreated && (
          <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs" data-testid="team-sous-traitant-created">
            <p className="font-semibold text-emerald-900">Compte créé ✓</p>
            <p className="text-emerald-800 mt-0.5">Communiquez ces identifiants au sous-traitant :</p>
            <p className="mt-1"><span className="text-slate-500">Email :</span> <span className="font-mono">{lastCreated.email}</span></p>
            <p><span className="text-slate-500">Mot de passe :</span> <span className="font-mono">{lastCreated.password}</span></p>
            <button onClick={() => setLastCreated(null)} className="mt-2 text-emerald-700 hover:text-emerald-900 underline">Masquer</button>
          </div>
        )}
      </div>
    </Card>
  );
}
