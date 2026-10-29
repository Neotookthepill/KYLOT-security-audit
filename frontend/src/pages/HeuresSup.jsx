import React, { useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { ChevronLeft, ChevronRight, Calendar as CalendarIcon, Clock, Loader2, ShieldCheck, AlertTriangle, Check, X, Pencil, Ban, History } from "lucide-react";
import { toast } from "sonner";
import { currentMonth, shiftMonth, monthLabel } from "@/lib/saleConstants";
import { useAuth } from "@/contexts/AuthContext";
import { Link } from "react-router-dom";
import OvertimeAccessDialog from "@/components/OvertimeAccessDialog";

const WEEKDAYS_FR = ["L", "M", "M", "J", "V", "S", "D"];

function daysInMonth(yyyyMM) {
  const [y, m] = yyyyMM.split("-").map(Number);
  return new Date(y, m, 0).getDate();
}
function toISO(yyyyMM, d) { return `${yyyyMM}-${String(d).padStart(2, "0")}`; }
function weekdayLetter(yyyyMM, d) {
  const [y, m] = yyyyMM.split("-").map(Number);
  const idx = (new Date(y, m - 1, d).getDay() + 6) % 7;
  return WEEKDAYS_FR[idx];
}
function isWeekend(yyyyMM, d) {
  const [y, m] = yyyyMM.split("-").map(Number);
  const wd = new Date(y, m - 1, d).getDay();
  return wd === 0 || wd === 6;
}
function isToday(yyyyMM, d) {
  const t = new Date();
  const iso = toISO(yyyyMM, d);
  const today = `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}-${String(t.getDate()).padStart(2, "0")}`;
  return iso === today;
}

function HoursCell({ techName, date, entry, isAdmin, onSaved, onValidated, onRefuseRequest }) {
  const [val, setVal] = useState(entry ? String(entry.hours) : "");
  const [saving, setSaving] = useState(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { setVal(entry ? String(entry.hours) : ""); }, [entry?.hours]);

  const commit = async () => {
    const trimmed = val.trim().replace(",", ".");
    const num = trimmed === "" ? 0 : parseFloat(trimmed);
    if (isNaN(num) || num < 0 || num > 24) { toast.error("Heures invalides (0–24)"); setVal(entry ? String(entry.hours) : ""); return; }
    if (num === (entry?.hours || 0)) return;
    setSaving(true);
    try {
      const { data: saved } = await api.post("/overtime", { technician_name: techName, date, hours: num });
      onSaved?.(techName, date, num, saved);
    } catch (err) {
      toast.error(formatApiError(err));
      setVal(entry ? String(entry.hours) : "");
    } finally { setSaving(false); }
  };

  const status = entry?.status;
  const approved = status === "approved";
  const refused = status === "refused";
  const pending = entry && status !== "approved" && status !== "refused";
  const validateOne = async (e) => {
    e.stopPropagation();
    if (!entry?.id) return;
    try {
      await api.put(`/overtime/${entry.id}/validate`);
      onValidated?.(entry.id);
      toast.success("Validé ✓");
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const titleText = approved ? "Validé"
    : refused ? `Refusé${entry?.refused_reason ? ` — ${entry.refused_reason}` : ""}`
    : pending ? "À valider" : "";

  return (
    <div className="relative group">
      <input
        type="text"
        inputMode="decimal"
        value={val}
        onChange={(e) => setVal(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); if (e.key === "Escape") setVal(entry ? String(entry.hours) : ""); }}
        disabled={saving}
        placeholder="—"
        className={`w-full h-10 sm:h-9 px-1 text-center text-sm sm:text-xs rounded font-semibold focus:outline-none focus:ring-2 focus:ring-slate-900
          ${approved ? "border border-emerald-400 bg-emerald-50 text-emerald-900" :
            refused ? "border border-red-400 bg-red-50 text-red-900 line-through" :
            pending ? "border border-dashed border-amber-400 bg-amber-50 text-amber-900" :
            "border border-transparent hover:border-slate-200 focus:border-slate-300 text-slate-800 font-normal"}`}
        title={titleText}
        data-testid={`overtime-cell-${techName}-${date}`}
      />
      {(pending || approved) && isAdmin && (
        <div className="absolute -top-1 -right-1 flex gap-0.5 opacity-0 group-hover:opacity-100 transition">
          {pending && (
            <button
              onClick={validateOne}
              className="h-4 w-4 rounded-full bg-white border border-emerald-300 grid place-items-center hover:bg-emerald-50"
              title="Valider"
              data-testid={`overtime-validate-${techName}-${date}`}
            ><Check size={9} className="text-emerald-700" /></button>
          )}
          <button
            onClick={(e) => { e.stopPropagation(); if (entry?.id) onRefuseRequest?.(entry); }}
            className="h-4 w-4 rounded-full bg-white border border-red-300 grid place-items-center hover:bg-red-50"
            title="Refuser (avec motif)"
            data-testid={`overtime-refuse-${techName}-${date}`}
          ><Ban size={9} className="text-red-700" /></button>
        </div>
      )}
      {refused && (
        <div className="absolute -top-1 -right-1">
          <span className="inline-block h-3 w-3 rounded-full bg-red-500 border border-white" title={titleText} />
        </div>
      )}
    </div>
  );
}


function RefuseDialog({ open, onOpenChange, entry, onDone }) {
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (open) setReason(entry?.refused_reason || ""); }, [open, entry]);
  const submit = async () => {
    if (!entry?.id) return;
    setSaving(true);
    try {
      await api.post(`/overtime/${entry.id}/refuse`, { reason: reason.trim() || null });
      toast.success("Saisie refusée. Technicien notifié.");
      onDone?.(entry.id, reason.trim());
      onOpenChange(false);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setSaving(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Refuser la saisie</DialogTitle>
          <DialogDescription>
            {entry ? <>Vous refusez <b>{entry.hours}h</b> de <b>{entry.technician_name}</b> le <b>{entry.date}</b>. Le technicien sera notifié.</> : null}
          </DialogDescription>
        </DialogHeader>
        <div className="py-2">
          <label className="text-xs uppercase tracking-widest text-slate-500">Motif (visible par le technicien)</label>
          <Textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Ex : journée déjà validée, heures non demandées, dépassement non autorisé…"
            className="mt-1"
            rows={3}
            maxLength={500}
            data-testid="overtime-refuse-reason"
          />
        </div>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>Annuler</Button>
          <Button variant="destructive" onClick={submit} disabled={saving} data-testid="overtime-refuse-submit">
            {saving ? <Loader2 size={14} className="animate-spin mr-1" /> : <Ban size={14} className="mr-1" />} Refuser
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


function HistoryPanel({ isTech }) {
  const [loading, setLoading] = useState(false);
  const [months, setMonths] = useState([]);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const { data } = await api.get("/overtime/history?months=6");
        if (!cancelled) setMonths(data.months || []);
      } catch (err) {
        if (!cancelled) toast.error(formatApiError(err));
      } finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, []);
  // For tech: flatten (one entry per month for himself)
  const summary = useMemo(() => {
    return months.map((m) => {
      const rows = m.rows || [];
      const approved = rows.reduce((s, r) => s + (r.approved_hours || 0), 0);
      const pending = rows.reduce((s, r) => s + (r.pending_hours || 0), 0);
      const refused = rows.reduce((s, r) => s + (r.refused_hours || 0), 0);
      return { month: m.month, approved: Math.round(approved * 100) / 100, pending: Math.round(pending * 100) / 100, refused: Math.round(refused * 100) / 100 };
    });
  }, [months]);
  return (
    <Card className="p-4 border-slate-200 shadow-sm mt-6" data-testid="overtime-history">
      <div className="flex items-center gap-2 mb-3">
        <History size={16} className="text-slate-400" />
        <p className="font-display text-lg font-semibold">Historique {isTech ? "de mes heures" : "6 derniers mois"}</p>
        {loading && <Loader2 size={12} className="animate-spin text-slate-400" />}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {summary.map((m) => (
          <div key={m.month} className="rounded-lg border border-slate-200 p-3 bg-white/60">
            <p className="text-[11px] uppercase tracking-widest text-slate-500 capitalize">{monthLabel(m.month)}</p>
            <p className="font-display text-2xl font-semibold mt-1">{m.approved}<span className="text-sm text-slate-500 font-normal ml-0.5">h</span></p>
            <p className="text-[11px] text-emerald-700 mt-0.5">validées</p>
            {m.pending > 0 && <p className="text-[11px] text-amber-700 mt-0.5">{m.pending}h à valider</p>}
            {m.refused > 0 && <p className="text-[11px] text-red-700 mt-0.5">{m.refused}h refusées</p>}
            {m.approved === 0 && m.pending === 0 && m.refused === 0 && <p className="text-[11px] text-slate-400 mt-0.5">Aucune saisie</p>}
          </div>
        ))}
      </div>
    </Card>
  );
}

export default function HeuresSup() {
  const { user, can } = useAuth();
  const isAdmin = can("overtime", "validate");
  const canManageAccess = can("users", "manage");
  const isTech = user?.role === "technicien";
  const [month, setMonth] = useState(currentMonth());
  const [data, setData] = useState({ entries: [], rows: [], grand_total: 0, threshold: 30 });
  const [loading, setLoading] = useState(false);
  const [accessOpen, setAccessOpen] = useState(false);
  const [refuseTarget, setRefuseTarget] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.get(`/overtime?month=${month}`);
      setData(r.data);
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [month]);

  const days = useMemo(() => Array.from({ length: daysInMonth(month) }, (_, i) => i + 1), [month]);

  // entriesByTech[name][date] = { id, hours, status }
  const byTech = useMemo(() => {
    const m = {};
    for (const e of data.entries || []) {
      m[e.technician_name] = m[e.technician_name] || {};
      m[e.technician_name][e.date] = e;
    }
    return m;
  }, [data]);

  // Preserve name-order to avoid rows jumping while typing
  const orderedRows = useMemo(() => [...(data.rows || [])].sort((a, b) => a.technician_name.localeCompare(b.technician_name, "fr")), [data.rows]);

  const overThresholdRows = orderedRows.filter((r) => r.over_threshold);

  const optimisticUpdate = (techName, date, hours, savedEntry) => {
    setData((prev) => {
      const others = (prev.entries || []).filter((e) => !(e.technician_name === techName && e.date === date));
      let entries;
      if (hours > 0) {
        // Merge server-returned fields (id, status) when available
        const merged = savedEntry
          ? { technician_name: techName, date, hours, status: savedEntry.status || "pending", id: savedEntry.id }
          : { technician_name: techName, date, hours, status: "pending" };
        entries = [...others, merged];
      } else {
        entries = others;
      }
      return computeTotals(prev, entries);
    });
    toast.success(`${techName} · ${hours}h enregistrée${hours > 1 ? "s" : ""}`);
  };

  const optimisticValidate = (entryId) => {
    setData((prev) => {
      const entries = (prev.entries || []).map((e) => (e.id === entryId ? { ...e, status: "approved" } : e));
      return computeTotals(prev, entries);
    });
  };

  const validateAllForTech = async (techName) => {
    try {
      const { data: res } = await api.post("/overtime/validate-tech", { technician_name: techName, month });
      toast.success(`${res.validated} entrée(s) validée(s) pour ${techName}`);
      load();
    } catch (err) { toast.error(formatApiError(err)); }
  };

  const computeTotals = (prev, entries) => {
    const approved = {}, pending = {}, refused = {};
    for (const e of entries) {
      const bucket = e.status === "approved" ? approved : e.status === "refused" ? refused : pending;
      bucket[e.technician_name] = (bucket[e.technician_name] || 0) + Number(e.hours || 0);
    }
    const threshold = prev.threshold || 0;
    const rows = prev.rows.map((r) => {
      const a = Math.round((approved[r.technician_name] || 0) * 100) / 100;
      const p = Math.round((pending[r.technician_name] || 0) * 100) / 100;
      const rf = Math.round((refused[r.technician_name] || 0) * 100) / 100;
      const total = Math.round((a + p) * 100) / 100;
      return { ...r, approved_hours: a, pending_hours: p, refused_hours: rf, total_hours: total, over_threshold: threshold > 0 && total >= threshold };
    });
    const grand_total = Math.round(rows.reduce((s, r) => s + r.total_hours, 0) * 100) / 100;
    return { ...prev, entries, rows, grand_total };
  };

  const optimisticRefuse = (entryId, reason) => {
    setData((prev) => {
      const entries = (prev.entries || []).map((e) => (e.id === entryId ? { ...e, status: "refused", refused_reason: reason || null } : e));
      return computeTotals(prev, entries);
    });
  };

  return (
    <div className="p-4 md:p-8 max-w-[1500px]">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-6 flex-wrap gap-3">
        <div>
          <p className="overline">Suivi</p>
          <h1 className="font-display text-3xl md:text-4xl font-semibold tracking-tight">Heures sup techniciens</h1>
          <p className="text-sm text-slate-500 mt-2">Saisie journalière → statut « à valider » → l'admin ou le responsable valide. {data.threshold > 0 ? `Alerte au seuil de ${data.threshold}h.` : "Alerte désactivée."}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="icon" onClick={() => setMonth(shiftMonth(month, -1))} data-testid="overtime-prev" aria-label="Mois précédent"><ChevronLeft size={16} /></Button>
          <div className="font-display text-lg font-semibold w-40 sm:w-52 text-center capitalize flex items-center justify-center gap-2" data-testid="overtime-month-label">
            <CalendarIcon size={16} className="text-slate-400" />
            {monthLabel(month)}
          </div>
          <Button variant="outline" size="icon" onClick={() => setMonth(shiftMonth(month, 1))} data-testid="overtime-next" aria-label="Mois suivant"><ChevronRight size={16} /></Button>
          {month !== currentMonth() && (
            <Button variant="ghost" size="sm" onClick={() => setMonth(currentMonth())}>Ce mois</Button>
          )}
        </div>
      </div>

      {overThresholdRows.length > 0 && (
        <div className="mb-6 rounded-xl bg-red-50 border border-red-200 p-4 flex items-start gap-3" data-testid="overtime-alert">
          <AlertTriangle size={18} className="text-red-600 mt-0.5 shrink-0" />
          <div className="flex-1 text-sm text-red-900">
            <p className="font-semibold">Seuil d'alerte atteint</p>
            <p className="text-xs text-red-800/90 mt-0.5">
              {overThresholdRows.map((r) => `${r.technician_name} (${r.total_hours}h / seuil ${r.threshold ?? data.threshold}h)`).join(" · ")}
            </p>
          </div>
          {isAdmin && (
            <Link to="/parametres#overtime-threshold" className="text-xs text-red-700 underline hover:text-red-900">Ajuster le seuil</Link>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 mb-6">
        {orderedRows.length === 0 && !loading && (
          <p className="text-sm text-slate-500 col-span-full">Aucun technicien. Ajoute-en dans Utilisateurs → Équipe.</p>
        )}
        {orderedRows.map((r) => (
          <Card key={r.technician_name} className={`p-4 border shadow-sm ${r.over_threshold ? "border-red-300 bg-red-50/30" : "border-slate-200"}`} data-testid={`overtime-summary-${r.technician_name}`}>
            <div className="flex items-start justify-between">
              <div className="flex-1 min-w-0">
                <p className="text-xs text-slate-500 uppercase tracking-widest flex items-center gap-1.5">
                  {r.technician_name}
                  {r.over_threshold && <AlertTriangle size={11} className="text-red-500" />}
                </p>
                <p className="font-display text-3xl font-semibold tracking-tight mt-2">
                  {r.total_hours}
                  <span className="text-lg text-slate-500 font-normal ml-1">h</span>
                </p>
                <p className="text-[11px] text-slate-500 mt-1 flex items-center gap-2">
                  {r.approved_hours > 0 && <span className="inline-flex items-center gap-0.5 text-emerald-700"><ShieldCheck size={10} />{r.approved_hours}h validées</span>}
                  {r.pending_hours > 0 && <span className="inline-flex items-center gap-0.5 text-amber-700"><Clock size={10} />{r.pending_hours}h à valider</span>}
                  {r.total_hours === 0 && <span className="text-slate-400">sur {monthLabel(month)}</span>}
                </p>
                {isAdmin && r.pending_hours > 0 && (
                  <button
                    onClick={() => validateAllForTech(r.technician_name)}
                    className="mt-2 text-[11px] text-emerald-700 hover:text-emerald-900 underline inline-flex items-center gap-1"
                    data-testid={`overtime-validate-all-${r.technician_name}`}
                  ><Check size={11} /> Tout valider</button>
                )}
              </div>
              <div className={`h-9 w-9 rounded-lg grid place-items-center ${r.over_threshold ? "bg-red-100 text-red-700" : r.total_hours > 0 ? "bg-amber-50 text-amber-700" : "bg-slate-100 text-slate-400"}`}>
                <Clock size={16} />
              </div>
            </div>
          </Card>
        ))}
      </div>

      <Card className="border-slate-200 shadow-sm overflow-hidden">
        <div className="p-4 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div>
              <p className="font-display text-lg font-semibold">Saisie journalière</p>
              <p className="text-xs text-slate-500 mt-0.5">
                <span className="inline-block w-2 h-2 rounded-sm border border-dashed border-amber-400 bg-amber-50 mr-1 align-middle" /> à valider &nbsp;·&nbsp;
                <span className="inline-block w-2 h-2 rounded-sm border border-emerald-400 bg-emerald-50 mr-1 align-middle" /> validé &nbsp;·&nbsp;
                <span className="inline-block w-2 h-2 rounded-sm border border-red-400 bg-red-50 mr-1 align-middle" /> refusé
              </p>
            </div>
            {canManageAccess && (
              <button
                onClick={() => setAccessOpen(true)}
                className="ml-1 h-8 w-8 grid place-items-center rounded-lg text-slate-500 hover:text-slate-900 hover:bg-slate-100 transition"
                title="Gérer les personnes éligibles aux heures sup"
                aria-label="Gérer les personnes éligibles aux heures sup"
                data-testid="overtime-access-btn"
              >
                <Pencil size={16} />
              </button>
            )}
          </div>
          <div className="text-xs text-slate-500 flex items-center gap-3">
            {loading && <span className="inline-flex items-center gap-1"><Loader2 size={12} className="animate-spin" /> Chargement…</span>}
            <span>Total mois : <span className="font-display text-base font-semibold text-slate-900">{data.grand_total}h</span></span>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="text-sm border-collapse">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/60">
                <th className="sticky left-0 z-10 bg-slate-50 px-3 py-2 text-left overline min-w-[140px]">Technicien</th>
                {days.map((d) => (
                  <th key={d} className={`px-1 py-2 text-center min-w-[46px] sm:min-w-[42px] ${isWeekend(month, d) ? "bg-slate-100" : ""} ${isToday(month, d) ? "bg-indigo-50" : ""}`}>
                    <div className="text-[10px] text-slate-500 font-normal">{weekdayLetter(month, d)}</div>
                    <div className={`font-display text-sm ${isToday(month, d) ? "text-indigo-700 font-bold" : ""}`}>{d}</div>
                  </th>
                ))}
                <th className="sticky right-0 z-10 bg-slate-50 px-4 py-2 text-right overline min-w-[80px]">Total</th>
              </tr>
            </thead>
            <tbody>
              {orderedRows.length === 0 && (
                <tr><td colSpan={days.length + 2} className="p-8 text-center text-slate-500">Aucun technicien à afficher.</td></tr>
              )}
              {orderedRows.map((r) => (
                <tr key={r.technician_name} className="border-b border-slate-100 last:border-0 hover:bg-slate-50/30" data-testid={`overtime-row-${r.technician_name}`}>
                  <td className="sticky left-0 z-10 bg-white px-3 py-1 font-medium whitespace-nowrap">{r.technician_name}</td>
                  {days.map((d) => {
                    const iso = toISO(month, d);
                    const entry = byTech[r.technician_name]?.[iso];
                    return (
                      <td key={d} className={`p-0.5 ${isWeekend(month, d) ? "bg-slate-50/60" : ""} ${isToday(month, d) ? "bg-indigo-50/40" : ""}`}>
                        <HoursCell techName={r.technician_name} date={iso} entry={entry} isAdmin={isAdmin} onSaved={optimisticUpdate} onValidated={optimisticValidate} onRefuseRequest={setRefuseTarget} />
                      </td>
                    );
                  })}
                  <td className={`sticky right-0 z-10 bg-white px-4 py-1 text-right font-display font-semibold whitespace-nowrap ${r.over_threshold ? "text-red-700" : r.total_hours > 0 ? "text-amber-800" : "text-slate-400"}`}>
                    {r.total_hours}h
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {canManageAccess && (
        <OvertimeAccessDialog open={accessOpen} onOpenChange={setAccessOpen} onChanged={load} />
      )}

      <HistoryPanel isTech={isTech} />

      <RefuseDialog
        open={!!refuseTarget}
        onOpenChange={(v) => { if (!v) setRefuseTarget(null); }}
        entry={refuseTarget}
        onDone={optimisticRefuse}
      />
    </div>
  );
}
