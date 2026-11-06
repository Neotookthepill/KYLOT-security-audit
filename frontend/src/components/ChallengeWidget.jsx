import React, { useEffect, useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";
import useTeam from "@/lib/useTeam";
import { Trophy, CalendarDays, Gift, Plus, Pencil, History, XCircle, Users, Crown } from "lucide-react";

const fmtEur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);
const fmtDate = (iso) => {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
};
const CRITERIA = {
  assist: "Assistances",
  r1: "R1",
  sales: "Ventes signées",
  ca: "Chiffre d'affaires",
};
const MEDALS = ["🥇", "🥈", "🥉"];

const emptyForm = () => ({
  name: "",
  start_date: "",
  end_date: "",
  criterion: "assist",
  participant_names: [],
  rewards: [
    { place: 1, amount: 1250 },
    { place: 2, amount: 500 },
    { place: 3, amount: 250 },
  ],
});

function pointsLabel(row, criterion) {
  if (criterion === "ca") return fmtEur(row.points);
  if (criterion === "r1") return `${row.count} R1`;
  if (criterion === "sales") return `${row.count} vente${row.count > 1 ? "s" : ""}`;
  return `${row.count} assistance${row.count > 1 ? "s" : ""}`;
}

export default function ChallengeWidget() {
  const { user } = useAuth();
  const { commerciaux } = useTeam();
  const [data, setData] = useState({ challenge: null, ranking: [], me: null, days_left: 0 });
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [history, setHistory] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const isAdmin = user?.role === "admin";

  const load = async () => {
    try {
      setData((await api.get("/challenges/current")).data || { challenge: null, ranking: [], me: null, days_left: 0 });
    } catch (_) {
      /* garder l'affichage précédent */
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 90_000);
    const onFocus = () => load();
    window.addEventListener("focus", onFocus);
    return () => { clearInterval(id); window.removeEventListener("focus", onFocus); };
  }, []);

  const participants = useMemo(() => {
    const names = (commerciaux || []).map((c) => c.name).filter(Boolean);
    return [...new Set(names)];
  }, [commerciaux]);

  const startCreate = () => {
    setEditing(null);
    setForm({ ...emptyForm(), participant_names: participants });
    setOpen(true);
  };

  const startChristmas = () => {
    setEditing(null);
    setForm({
      name: "Challenge de Noël 2026",
      start_date: "2026-11-01",
      end_date: "2026-12-17",
      criterion: "assist",
      participant_names: participants,
      rewards: [
        { place: 1, amount: 1250 },
        { place: 2, amount: 500 },
        { place: 3, amount: 250 },
      ],
    });
    setOpen(true);
  };

  const startEdit = () => {
    const ch = data.challenge;
    if (!ch) return;
    setEditing(ch);
    setForm({
      name: ch.name,
      start_date: ch.start_date,
      end_date: ch.end_date,
      criterion: ch.criterion,
      participant_names: ch.participant_names || [],
      rewards: (ch.rewards || []).length
        ? ch.rewards
        : [{ place: 1, amount: 0 }, { place: 2, amount: 0 }, { place: 3, amount: 0 }],
    });
    setOpen(true);
  };

  const toggleParticipant = (name) => {
    setForm((f) => ({
      ...f,
      participant_names: f.participant_names.includes(name)
        ? f.participant_names.filter((n) => n !== name)
        : [...f.participant_names, name],
    }));
  };

  const save = async () => {
    if (!form.name.trim() || !form.start_date || !form.end_date) {
      return toast.error("Nom et dates obligatoires");
    }
    setSaving(true);
    try {
      const payload = {
        ...form,
        participant_names: form.participant_names.length ? form.participant_names : participants,
        rewards: form.rewards.filter((r) => Number(r.amount) > 0),
      };
      if (editing) {
        await api.put(`/challenges/${editing.id}`, payload);
        toast.success("Challenge mis à jour");
      } else {
        await api.post("/challenges", payload);
        toast.success("Challenge lancé");
      }
      setOpen(false);
      setEditing(null);
      await load();
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setSaving(false);
    }
  };

  const closeChallenge = async () => {
    if (!data.challenge) return;
    if (!window.confirm(`Clôturer « ${data.challenge.name} » ? Le classement sera figé.`)) return;
    try {
      await api.post(`/challenges/${data.challenge.id}/close`);
      toast.success("Challenge clôturé");
      await load();
    } catch (err) {
      toast.error(formatApiError(err));
    }
  };

  const openHistory = async () => {
    try {
      setHistory((await api.get("/challenges?include_closed=1")).data || []);
      setHistoryOpen(true);
    } catch (err) {
      toast.error(formatApiError(err));
    }
  };

  const ch = data.challenge;
  const ranking = data.ranking || [];
  const podium = ranking.slice(0, 3);

  return (
    <>
      <Card className="p-5 border-slate-200 shadow-sm" data-testid="challenge-widget">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="h-10 w-10 rounded-lg bg-amber-100 text-amber-700 grid place-items-center"><Trophy size={20} /></span>
            <div>
              <p className="overline">Challenge commercial</p>
              <p className="font-display text-xl font-semibold">{ch ? ch.name : "Aucun challenge en cours"}</p>
            </div>
          </div>
          {isAdmin && (
            <div className="flex flex-wrap gap-2">
              {ch ? (
                <>
                  <Button variant="outline" size="sm" onClick={startEdit}><Pencil size={13} className="mr-1" /> Modifier</Button>
                  <Button variant="outline" size="sm" onClick={closeChallenge}><XCircle size={13} className="mr-1" /> Clôturer</Button>
                </>
              ) : (
                <>
                  <Button size="sm" onClick={startChristmas} data-testid="challenge-christmas-btn"><Plus size={13} className="mr-1" /> Noël 2026</Button>
                  <Button variant="outline" size="sm" onClick={startCreate}><Plus size={13} className="mr-1" /> Créer</Button>
                </>
              )}
              <Button variant="ghost" size="sm" onClick={openHistory}><History size={13} className="mr-1" /> Historique</Button>
            </div>
          )}
        </div>

        {loading && <p className="text-sm text-slate-500 mt-4">Chargement du challenge…</p>}

        {!loading && !ch && (
          <p className="text-sm text-slate-600 mt-4">
            Aucun challenge actif. {isAdmin ? "Lancez le challenge de Noël ou créez un challenge personnalisé." : "Le prochain challenge sera affiché ici."}
          </p>
        )}

        {!loading && ch && (
          <>
            <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-slate-500">
              <span className="inline-flex items-center gap-1"><CalendarDays size={13} /> {fmtDate(ch.start_date)} → {fmtDate(ch.end_date)}</span>
              <span>{data.days_left} jour{data.days_left > 1 ? "s" : ""} restant{data.days_left > 1 ? "s" : ""}</span>
              <span className="inline-flex items-center gap-1"><Users size={13} /> {ranking.length} participant{ranking.length > 1 ? "s" : ""}</span>
              <span className="inline-flex items-center gap-1"><Gift size={13} /> {ch.criterion_label}</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-5">
              {podium.map((row, index) => (
                <div
                  key={row.name}
                  className={`rounded-xl border p-4 text-center ${index === 0 ? "border-amber-300 bg-amber-50/70" : "border-slate-200 bg-white"} ${row.is_me ? "ring-2 ring-indigo-400" : ""}`}
                  data-testid={`challenge-podium-${index + 1}`}
                >
                  <div className="text-3xl">{MEDALS[index]}</div>
                  <p className="font-semibold mt-1 truncate">{row.name}</p>
                  <p className="font-display text-2xl font-semibold mt-1">{pointsLabel(row, ch.criterion)}</p>
                  <p className="text-[11px] text-slate-500 mt-1">{row.is_me ? "Vous" : `#${row.rank}`}</p>
                </div>
              ))}
            </div>

            <div className="mt-4 rounded-lg border border-slate-200 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left">
                  <tr>
                    <th className="px-3 py-2 overline">Rang</th>
                    <th className="px-3 py-2 overline">Commercial</th>
                    <th className="px-3 py-2 overline text-right">{ch.criterion_label}</th>
                    <th className="px-3 py-2 overline text-right">CA</th>
                  </tr>
                </thead>
                <tbody>
                  {ranking.map((row) => (
                    <tr key={row.name} className={`border-t border-slate-100 ${row.is_me ? "bg-indigo-50/70 font-medium" : ""}`} data-testid={`challenge-row-${row.name}`}>
                      <td className="px-3 py-2">{row.rank <= 3 ? MEDALS[row.rank - 1] : row.rank}</td>
                      <td className="px-3 py-2">{row.name} {row.is_me && <span className="text-[10px] text-indigo-600">(vous)</span>}</td>
                      <td className="px-3 py-2 text-right">{pointsLabel(row, ch.criterion)}</td>
                      <td className="px-3 py-2 text-right text-slate-500">{fmtEur(row.ca)}</td>
                    </tr>
                  ))}
                  {!ranking.length && <tr><td colSpan={4} className="px-3 py-4 text-center text-slate-500">Aucune vente comptabilisée.</td></tr>}
                </tbody>
              </table>
            </div>

            {!!(ch.rewards || []).length && (
              <div className="flex flex-wrap gap-2 mt-3">
                {ch.rewards.map((r) => (
                  <span key={r.place} className="text-xs rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-amber-800">
                    {MEDALS[r.place - 1] || `#${r.place}`} {fmtEur(r.amount)}
                  </span>
                ))}
              </div>
            )}

            {data.me && (
              <p className="text-xs text-slate-500 mt-3">
                Ta position : <b className="text-slate-900">#{data.me.rank}</b> — {pointsLabel(data.me, ch.criterion)}
              </p>
            )}
          </>
        )}
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-xl" data-testid="challenge-dialog">
          <DialogHeader>
            <DialogTitle className="font-display text-2xl">{editing ? "Modifier le challenge" : "Nouveau challenge"}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div><Label>Nom</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Challenge de Noël 2026" /></div>
            <div className="grid grid-cols-2 gap-2">
              <div><Label>Début</Label><Input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} /></div>
              <div><Label>Fin</Label><Input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} /></div>
            </div>
            <div>
              <Label>Critère</Label>
              <select value={form.criterion} onChange={(e) => setForm({ ...form, criterion: e.target.value })} className="mt-1 h-9 w-full rounded-md border border-slate-200 bg-white px-3 text-sm">
                {Object.entries(CRITERIA).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            <div>
              <Label>Participants</Label>
              <div className="mt-1 max-h-32 overflow-auto rounded-md border border-slate-200 p-2 grid grid-cols-1 sm:grid-cols-2 gap-1">
                {participants.map((name) => (
                  <label key={name} className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={form.participant_names.includes(name)} onChange={() => toggleParticipant(name)} />
                    {name}
                  </label>
                ))}
                {!participants.length && <p className="text-xs text-slate-500">Aucun commercial dans l'équipe.</p>}
              </div>
            </div>
            <div>
              <Label>Récompenses</Label>
              <div className="grid grid-cols-3 gap-2 mt-1">
                {[0, 1, 2].map((i) => (
                  <div key={i}>
                    <p className="text-[11px] text-slate-500">{MEDALS[i]} {i + 1}e</p>
                    <Input
                      type="number" min={0} value={form.rewards[i]?.amount ?? 0}
                      onChange={(e) => {
                        const rewards = [...form.rewards];
                        rewards[i] = { place: i + 1, amount: Number(e.target.value || 0) };
                        setForm({ ...form, rewards });
                      }}
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="outline" onClick={() => setOpen(false)}>Annuler</Button>
            <Button onClick={save} disabled={saving}>{saving ? "Enregistrement…" : "Enregistrer"}</Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={historyOpen} onOpenChange={setHistoryOpen}>
        <DialogContent className="sm:max-w-2xl" data-testid="challenge-history-dialog">
          <DialogHeader><DialogTitle className="font-display text-2xl">Historique des challenges</DialogTitle></DialogHeader>
          <div className="max-h-[60vh] overflow-auto space-y-3">
            {history.map((h) => (
              <div key={h.id} className="rounded-lg border border-slate-200 p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold">{h.name}</p>
                  <span className="text-xs text-slate-500">{fmtDate(h.start_date)} → {fmtDate(h.end_date)} · {h.status}</span>
                </div>
                <p className="text-xs text-slate-500 mt-1">{h.criterion_label}</p>
                {h.results_snapshot?.ranking?.length ? (
                  <div className="mt-2 text-sm">
                    {h.results_snapshot.ranking.slice(0, 3).map((r) => (
                      <div key={r.name} className="flex justify-between"><span>{MEDALS[r.rank - 1] || `#${r.rank}`} {r.name}</span><span>{pointsLabel(r, h.criterion)}</span></div>
                    ))}
                  </div>
                ) : <p className="text-xs text-slate-400 mt-2">Pas encore de classement figé.</p>}
              </div>
            ))}
            {!history.length && <p className="text-sm text-slate-500">Aucun challenge enregistré.</p>}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
