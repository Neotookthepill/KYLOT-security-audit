import React, { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ChevronLeft, ChevronRight, User, CalendarOff, Sun, Plus, Sparkles, RefreshCw } from "lucide-react";
import ProjectDialog from "@/components/ProjectDialog";
import AbsencesDialog from "@/components/AbsencesDialog";
import OffDaysDialog from "@/components/OffDaysDialog";
import EventDialog from "@/components/EventDialog";
import ReinterventionDialog from "@/components/ReinterventionDialog";
import useTeam from "@/lib/useTeam";
import { useAuth } from "@/contexts/AuthContext";

const MONTHS = ["Janvier","Février","Mars","Avril","Mai","Juin","Juillet","Août","Septembre","Octobre","Novembre","Décembre"];
const DAYS = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"];

// iter120 : "termine" (À encaisser) = bleu pétant · "encaisse" (Terminé validé) = vert émeraude
const statusColors = {
  a_planifier: "bg-slate-200 text-slate-800 border-slate-300 hover:bg-slate-300",
  en_cours: "bg-amber-100 text-amber-900 border-amber-300 hover:bg-amber-200",
  termine: "bg-blue-500 text-white border-blue-600 hover:bg-blue-600",
  encaisse: "bg-emerald-100 text-emerald-900 border-emerald-300 hover:bg-emerald-200",
};

export default function CalendarPage() {
  const { user, can, loading: authLoading } = useAuth();
  const { techniciens, sousTraitants } = useTeam();
  // iter140 : les sous-traitants apparaissent dans le planning admin comme les techniciens
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
  const [offDays, setOffDays] = useState([]);
  const [events, setEvents] = useState([]);
  const [reinters, setReinters] = useState([]);
  const [absOpen, setAbsOpen] = useState(false);
  const [offOpen, setOffOpen] = useState(false);
  const [eventOpen, setEventOpen] = useState(false);
  const [reinterOpen, setReinterOpen] = useState(false);
  const [reinterClient, setReinterClient] = useState(null);
  const [editingEvent, setEditingEvent] = useState(null);
  const [eventDefaultDate, setEventDefaultDate] = useState(null);
  const [editing, setEditing] = useState(null);
  const [filter, setFilter] = useState("__all");
  const [cursor, setCursor] = useState(() => {
    const d = new Date();
    return { y: d.getFullYear(), m: d.getMonth() };
  });

  const monthStr = `${cursor.y}-${String(cursor.m + 1).padStart(2, "0")}`;

  const load = async () => {
    // iter209 : endpoint dédié Planning — gated par `planning.view`, indépendant
    // de `projects.view`. Retirer « Chantiers » à un technicien ne vide plus son planning.
    try { setProjects((await api.get("/planning/projects")).data); }
    catch (_) { /* keep previous */ }
  };
  const loadAbsences = async () => {
    // iter159 : seuls admin/responsable/super_admin voient les absences des autres.
    if (!(user?.role === "admin" || user?.role === "responsable" || user?.role === "super_admin")) {
      setAbsences([]);
      return;
    }
    try { setAbsences((await api.get("/absences")).data || []); } catch (_) {}
  };
  const loadOffDays = async () => { try { setOffDays((await api.get(`/off-days?month=${monthStr}`)).data || []); } catch (_) {} };
  const loadEvents = async () => { try { setEvents((await api.get(`/events?month=${monthStr}`)).data || []); } catch (_) {} };
  const loadReinters = async () => { try { setReinters((await api.get(`/reinterventions?month=${monthStr}`)).data || []); } catch (_) {} };

  useEffect(() => {
    if (authLoading || !user?.id) return;
    load(); loadAbsences();
    const onFocus = () => { load(); loadAbsences(); loadOffDays(); loadEvents(); loadReinters(); };
    const onVis = () => { if (document.visibilityState === "visible") onFocus(); };
    // iter52: rafraîchir immédiatement quand une vente change de statut
    const onSalesUpdated = () => { load(); };
    // iter216 : synchronisation temps réel Kanban ↔ Planning — un statut modifié
    // sur le Kanban se reflète instantanément dans le Planning (et inversement).
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
  }, [authLoading, user?.id]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadOffDays(); loadEvents(); loadReinters(); }, [monthStr]);

  const canFilter = user?.role === "admin" || user?.role === "responsable";
  const canManageAbs = can("planning", "edit", "team");
  const isProspect = ["prospecteur", "responsable_prospecteur"].includes(user?.role);

  const visible = useMemo(() => {
    if (filter === "__all") return projects;
    if (filter === "__none") return projects.filter((p) => !p.assigned_to || (Array.isArray(p.assigned_to) && p.assigned_to.length === 0));
    return projects.filter((p) => {
      const list = Array.isArray(p.assigned_to) ? p.assigned_to : (p.assigned_to ? [p.assigned_to] : []);
      return list.map((n) => n.toLowerCase()).includes(filter.toLowerCase());
    });
  }, [projects, filter]);

  const cells = useMemo(() => {
    const first = new Date(cursor.y, cursor.m, 1);
    const startWeekday = (first.getDay() + 6) % 7;
    const daysInMonth = new Date(cursor.y, cursor.m + 1, 0).getDate();
    const arr = [];
    for (let i = 0; i < startWeekday; i++) arr.push(null);
    for (let d = 1; d <= daysInMonth; d++) arr.push(new Date(cursor.y, cursor.m, d));
    while (arr.length % 7 !== 0) arr.push(null);
    return arr;
  }, [cursor]);

  const absencesByDay = useMemo(() => {
    const map = {};
    for (const a of absences) {
      if (!/^\d{4}-\d{2}-\d{2}$/.test(a.date_from) || !/^\d{4}-\d{2}-\d{2}$/.test(a.date_to)) continue;
      if (filter !== "__all" && filter !== "__none") {
        if ((a.person_name || "").toLowerCase() !== filter.toLowerCase()) continue;
      }
      const start = new Date(a.date_from + "T00:00:00");
      const end = new Date(a.date_to + "T00:00:00");
      for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
        // iter45: clé locale (jamais toISOString() qui shift à cause du fuseau)
        const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
        map[key] = map[key] || [];
        map[key].push(a);
      }
    }
    return map;
  }, [absences, filter]);

  const offByDay = useMemo(() => {
    const map = {};
    for (const o of offDays) {
      if (filter !== "__all" && filter !== "__none" && o.scope === "person") {
        const names = (o.person_names || []).map((n) => n.toLowerCase());
        if (!names.includes(filter.toLowerCase())) continue;
      }
      map[o.date] = map[o.date] || [];
      map[o.date].push(o);
    }
    return map;
  }, [offDays, filter]);

  const eventsByDay = useMemo(() => {
    const map = {};
    for (const e of events) {
      map[e.date] = map[e.date] || [];
      map[e.date].push(e);
    }
    return map;
  }, [events]);

  const reintersByDay = useMemo(() => {
    const map = {};
    for (const r of reinters) {
      if (filter !== "__all" && filter !== "__none") {
        if ((r.technician_name || "").toLowerCase() !== filter.toLowerCase()) continue;
      }
      map[r.scheduled_date] = map[r.scheduled_date] || [];
      map[r.scheduled_date].push(r);
    }
    return map;
  }, [reinters, filter]);

  const projectsByDay = useMemo(() => {
    const map = {};
    for (const p of visible) {
      if (!p.scheduled_date || !/^\d{4}-\d{2}-\d{2}$/.test(p.scheduled_date)) continue;
      const dur = Math.max(1, Number(p.duration_days) || 1);
      const start = new Date(p.scheduled_date + "T00:00:00");
      // iter213 : construit la liste ordonnée des dates effectives du chantier
      // (consécutives + jours supplémentaires non consécutifs)
      const consecutiveKeys = [];
      for (let i = 0; i < dur; i++) {
        const d = new Date(start);
        d.setDate(d.getDate() + i);
        consecutiveKeys.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`);
      }
      const extras = (Array.isArray(p.extra_dates) ? p.extra_dates : []).filter((k) => /^\d{4}-\d{2}-\d{2}$/.test(k));
      const allKeys = [...consecutiveKeys, ...extras].sort();
      const total = allKeys.length;
      allKeys.forEach((key, idx) => {
        // iter211 : applique les exclusions ciblées à cette journée sur les noms affichés
        const excludedNames = new Set(((p.day_exclusions || {})[key] || []));
        const baseAssigned = Array.isArray(p.assigned_to) ? p.assigned_to : (p.assigned_to ? [p.assigned_to] : []);
        const effectiveAssigned = baseAssigned.filter((n) => !excludedNames.has(n));
        map[key] = map[key] || [];
        map[key].push({ ...p, assigned_to: effectiveAssigned, _dayIndex: idx, _totalDays: total, _cellDate: key });
      });
    }
    return map;
  }, [visible]);

  // iter45: format local YYYY-MM-DD (jamais toISOString() qui shift en UTC → -1 jour à Paris)
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const today = new Date();
  const todayIso = iso(today);

  const shift = (delta) => {
    const nm = cursor.m + delta;
    const y = cursor.y + Math.floor(nm / 12);
    const m = ((nm % 12) + 12) % 12;
    setCursor({ y, m });
  };

  const openNewEvent = (date) => { setEditingEvent(null); setEventDefaultDate(date || null); setEventOpen(true); };

  return (
    <div className="p-4 md:p-8 max-w-[1400px]">
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <p className="overline">Vue calendrier</p>
          <h1 className="font-display text-3xl sm:text-4xl font-semibold tracking-tight">Planning</h1>
          {(user?.role === "technicien" || user?.role === "sous_traitant") && <p className="text-sm text-slate-500 mt-2">Vous voyez uniquement vos chantiers.</p>}
          {isProspect && <p className="text-sm text-slate-500 mt-2" data-testid="calendar-prospect-note">Chantiers des clients issus de la prospection.</p>}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {canFilter && (
            <div className="flex items-center gap-2 w-full sm:w-auto">
              <User size={14} className="text-slate-500" />
              <Select value={filter} onValueChange={setFilter}>
                <SelectTrigger className="h-9 flex-1 sm:w-64 sm:flex-none" data-testid="calendar-filter"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all">Tous les techniciens & sous-traitants</SelectItem>
                  <SelectItem value="__none">Non assignés</SelectItem>
                  {assignables.map((t) => (
                    <SelectItem key={t.id} value={t.name}>
                      {t.name}{t._kind === "sous_traitant" ? " · S/T" : ""}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
          {canManageAbs && (
            <>
              <Button variant="outline" size="sm" onClick={() => openNewEvent(null)} data-testid="calendar-new-event" className="border-violet-200 text-violet-700 hover:bg-violet-50">
                <Sparkles size={14} className="mr-1.5" /> Événement
              </Button>
              <Button variant="outline" size="sm" onClick={() => setReinterOpen(true)} data-testid="calendar-reintervention" className="border-orange-200 text-orange-700 hover:bg-orange-50">
                <RefreshCw size={14} className="mr-1.5" /> Réintervention
              </Button>
              <Button variant="outline" size="sm" onClick={() => setOffOpen(true)} data-testid="calendar-off-days" className="border-slate-300 text-slate-600 hover:bg-slate-100">
                <Sun size={14} className="mr-1.5" /> Jours OFF
              </Button>
              <Button variant="outline" size="sm" onClick={() => setAbsOpen(true)} data-testid="calendar-manage-absences" className="border-red-200 text-red-700 hover:bg-red-50">
                <CalendarOff size={14} className="mr-1.5" /> Absences
              </Button>
            </>
          )}
          <div className="flex items-center gap-2 w-full sm:w-auto justify-between sm:justify-start">
            <Button variant="outline" size="icon" onClick={() => shift(-1)} data-testid="cal-prev" aria-label="Mois précédent"><ChevronLeft size={16} /></Button>
            <div className="font-display text-lg font-semibold sm:w-44 text-center capitalize">{MONTHS[cursor.m]} {cursor.y}</div>
            <Button variant="outline" size="icon" onClick={() => shift(1)} data-testid="cal-next" aria-label="Mois suivant"><ChevronRight size={16} /></Button>
          </div>
        </div>
      </div>

      <Card className="border-slate-200 shadow-sm overflow-hidden">
        <div className="grid grid-cols-7 border-b border-slate-200">
          {DAYS.map((d) => (
            <div key={d} className="px-3 py-2 overline border-r last:border-r-0 border-slate-200 text-center">{d}</div>
          ))}
        </div>
        <div className="grid grid-cols-7">
          {cells.map((cell, idx) => {
            const key = cell ? iso(cell) : `e-${idx}`;
            const cellIso = cell ? iso(cell) : null;
            const list = cell ? (projectsByDay[cellIso] || []) : [];
            const offs = cell ? (offByDay[cellIso] || []) : [];
            const dayEvents = cell ? (eventsByDay[cellIso] || []) : [];
            const isOff = offs.length > 0;
            const isToday = cell && cellIso === todayIso;
            return (
              <div
                key={key}
                className={`min-h-[110px] p-2 border-r border-b last:border-r-0 border-slate-100 relative ${cell ? (isOff ? "bg-slate-100/70" : "") : "bg-slate-50/50"}`}
                data-testid={cell ? `cal-day-${cellIso}` : undefined}
              >
                {cell && (
                  <>
                    <div className="flex items-center justify-between">
                      <div className={`text-xs font-semibold mb-1 ${isToday ? "text-blue-600" : isOff ? "text-slate-400" : "text-slate-500"}`}>{cell.getDate()}</div>
                      {canManageAbs && (
                        <button onClick={() => openNewEvent(cellIso)} className="opacity-0 hover:opacity-100 group-hover:opacity-100 text-slate-300 hover:text-violet-600 transition" title="Nouvel événement">
                          <Plus size={11} />
                        </button>
                      )}
                    </div>

                    {/* iter45: le grisage de la case suffit — aucun texte OFF affiché */}

                    {dayEvents.length > 0 && (
                      <div className="mb-1 space-y-0.5">
                        {dayEvents.slice(0, 2).map((ev) => (
                          <button
                            key={ev.id}
                            onClick={() => { setEditingEvent(ev); setEventDefaultDate(null); setEventOpen(true); }}
                            disabled={!canManageAbs}
                            className="w-full text-left text-[10px] px-1.5 py-0.5 rounded bg-violet-100 text-violet-800 border border-violet-300 hover:bg-violet-200 font-medium truncate"
                            title={`${ev.title}${ev.start_time ? " · " + ev.start_time : ""}${ev.description ? "\n" + ev.description : ""}`}
                            data-testid={`cal-event-item-${ev.id}`}
                          >
                            ✨ {ev.title}{ev.start_time ? ` · ${ev.start_time}` : ""}
                          </button>
                        ))}
                        {dayEvents.length > 2 && <div className="text-[10px] text-violet-700">+{dayEvents.length - 2}</div>}
                      </div>
                    )}

                    {(reintersByDay[cellIso] || []).length > 0 && (
                      <div className="mb-1 space-y-0.5">
                        {(reintersByDay[cellIso] || []).slice(0, 2).map((r) => (
                          <div
                            key={r.id}
                            role="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              if (isProspect) return;
                              // iter161 : ouvre la fiche réintervention de ce client (historique + ajout)
                              setReinterClient({ id: r.client_id, name: r.client_name });
                              setReinterOpen(true);
                            }}
                            className={`text-[10px] px-1.5 py-0.5 rounded border font-medium truncate cursor-pointer hover:brightness-95 ${r.status === "terminee" ? "bg-emerald-50 text-emerald-800 border-emerald-200" : "bg-orange-100 text-orange-800 border-orange-300"}`}
                            title={`Réinter — ${r.client_name || ""}${r.scheduled_time ? " · " + r.scheduled_time : ""}${r.technician_name ? " · " + r.technician_name : ""}${r.note ? "\n" + r.note : ""}`}
                            data-testid={`cal-reinter-${r.id}`}
                          >
                            🔄 {r.client_name || "Réinter"}{r.scheduled_time ? ` · ${r.scheduled_time}` : ""}
                          </div>
                        ))}
                        {(reintersByDay[cellIso] || []).length > 2 && <div className="text-[10px] text-orange-700">+{(reintersByDay[cellIso] || []).length - 2}</div>}
                      </div>
                    )}

                    {(absencesByDay[cellIso] || []).length > 0 && (
                      <div className="space-y-0.5 mb-1">
                        {(absencesByDay[cellIso] || []).slice(0, 2).map((a) => {
                          const partial = a.all_day === false && a.start_time && a.end_time;
                          return (
                            <div
                              key={a.id}
                              className={`text-[10px] px-1.5 py-0.5 rounded font-medium truncate ${partial ? "bg-amber-50 text-amber-800 border border-amber-200" : "bg-red-100 text-red-800 border border-red-200"}`}
                              title={`${partial ? "Absent partiel" : "Absent"} — ${a.person_name}${partial ? ` · ${a.start_time}–${a.end_time}` : ""}${a.reason ? " · " + a.reason : ""}${a.note ? "\n" + a.note : ""}`}
                              data-testid={`cal-absence-${a.id}-${cellIso}`}
                            >
                              {partial ? "⏱" : "🚫"} {a.person_name}{partial ? ` ${a.start_time}–${a.end_time}` : ""}
                            </div>
                          );
                        })}
                        {(absencesByDay[cellIso] || []).length > 2 && (
                          <div className="text-[10px] text-red-700">+{(absencesByDay[cellIso] || []).length - 2} absents</div>
                        )}
                      </div>
                    )}

                    <div className="space-y-1">
                      {/* iter172 : plus de troncature — tous les chantiers du jour doivent être
                          lisibles sans scroll interne. La cellule (`min-h-[110px]`) grandit
                          naturellement et la row CSS-grid s'aligne sur la cellule la plus haute. */}
                      {list.map((p) => {
                        const assigned = Array.isArray(p.assigned_to) ? p.assigned_to.join(", ") : (p.assigned_to || "");
                        const label = p._totalDays > 1 ? `${p.client_name} (${p._dayIndex + 1}/${p._totalDays})` : p.client_name;
                        // iter218 : le chantier bascule visuellement en « Terminé (encaissé) » (vert)
                        // dès que la vente passe en `argent_recupere` — le project.status reste
                        // `termine` en base tant que le cycle vente n'est pas explicitement clôturé.
                        const dayDone = !!(p.days_done && p.days_done[p._cellDate]);
                        const baseStatus = p._totalDays > 1 && dayDone && p.status !== "termine" && p.status !== "encaisse" ? "termine" : p.status;
                        const effectiveStatus = (p.sale_status === "argent_recupere") ? "encaisse" : baseStatus;
                        return (
                          <button
                            key={`${p.id}-${p._dayIndex}`}
                            onClick={() => { if (!isProspect) setEditing({ ...p, _contextDate: p._cellDate || cellIso }); }}
                            className={`w-full text-left text-[11px] px-1.5 py-1 rounded border transition-colors ${statusColors[effectiveStatus] || statusColors.a_planifier} truncate ${isProspect ? "cursor-default" : "cursor-pointer"}`}
                            title={isProspect ? `${p.client_name} — ${[p.client_address, p.client_postal_code, p.client_city].filter(Boolean).join(" ")}` : `${p.client_name} — ${p.service}${assigned ? " · " + assigned : ""}${p._totalDays > 1 ? " · Jour " + (p._dayIndex + 1) + "/" + p._totalDays : ""}`}
                            data-testid={`cal-event-${p.id}-${p._dayIndex}`}
                          >
                            <span className="font-medium">{label}</span>{isProspect ? ([p.client_address, p.client_city].filter(Boolean).length ? ` — ${[p.client_address, p.client_city].filter(Boolean).join(", ")}` : "") : ` — ${p.service}`}
                          </button>
                        );
                      })}
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </Card>

      <ProjectDialog project={editing} onClose={() => setEditing(null)} onSaved={load} contextDate={editing?._contextDate || null} />
      <AbsencesDialog open={absOpen} onOpenChange={setAbsOpen} onChanged={loadAbsences} />
      <OffDaysDialog open={offOpen} onOpenChange={setOffOpen} onChanged={loadOffDays} month={monthStr} />
      <EventDialog
        open={eventOpen}
        onOpenChange={(v) => { setEventOpen(v); if (!v) { setEditingEvent(null); setEventDefaultDate(null); } }}
        event={editingEvent}
        defaultDate={eventDefaultDate}
        onSaved={loadEvents}
      />
      <ReinterventionDialog open={reinterOpen} onOpenChange={(v) => { setReinterOpen(v); if (!v) setReinterClient(null); }} client={reinterClient} onChanged={loadReinters} />
    </div>
  );
}
