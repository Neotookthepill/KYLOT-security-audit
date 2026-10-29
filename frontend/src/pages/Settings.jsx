import React, { useEffect, useRef, useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Palette, Type, Image as ImageIcon, Save, RotateCcw, LayoutGrid, Clock, Bell, GripVertical, TrendingUp, Pencil, AlarmClock } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { useSettings, AVAILABLE_FONTS } from "@/contexts/SettingsContext";
import { SALE_STATUSES, orderStatuses } from "@/lib/saleConstants";
import api, { formatApiError } from "@/lib/api";
import BonusesDialog from "@/components/BonusesDialog";
import { ProspectMgrBonusesEditor, cleanMgrBonuses } from "@/components/ProspectMgrBonuses";
import StatusManagerDialog from "@/components/StatusManagerDialog";
import PerTechThresholdList from "@/components/PerTechThresholdList";

const PRESET_PRIMARY = ["#0f172a", "#111827", "#1e293b", "#0369a1", "#1d4ed8", "#7c3aed", "#059669", "#dc2626", "#ea580c", "#d97706"];
const PRESET_ACCENT = ["#6366f1", "#3b82f6", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#ec4899", "#a855f7"];

function fileToBase64(file, maxW = 512) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const img = new window.Image();
      img.onload = () => {
        const scale = Math.min(1, maxW / img.width);
        const c = document.createElement("canvas");
        c.width = Math.round(img.width * scale);
        c.height = Math.round(img.height * scale);
        c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
        resolve(c.toDataURL("image/png", 0.9));
      };
      img.onerror = reject;
      img.src = e.target.result;
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export default function Settings() {
  const { settings, update } = useSettings();
  const [form, setForm] = useState(settings);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef(null);
  const [bonusesOpen, setBonusesOpen] = useState(false);
  const [bonusCount, setBonusCount] = useState(0);
  const [statusManagerOpen, setStatusManagerOpen] = useState(false);

  // iter112 : ouvre en surbrillance la section ciblée par le hash (#overtime-threshold)
  useEffect(() => {
    if (typeof window === "undefined") return;
    const h = (window.location.hash || "").replace("#", "");
    if (!h) return;
    const el = document.getElementById(h);
    if (el) {
      setTimeout(() => {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.classList.add("ring-2", "ring-indigo-400", "ring-offset-2");
        setTimeout(() => el.classList.remove("ring-2", "ring-indigo-400", "ring-offset-2"), 2400);
      }, 200);
    }
  }, []);

  React.useEffect(() => { setForm(settings); }, [settings]);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get("/bonuses");
        if (!cancelled) setBonusCount((data || []).length);
      } catch (_) { /* ignore */ }
    })();
    return () => { cancelled = true; };
  }, [bonusesOpen]);

  const save = async () => {
    setSaving(true);
    try {
      await update({
        theme_primary: form.theme_primary,
        theme_accent: form.theme_accent,
        font_family: form.font_family,
        logo: form.logo || "",
        app_name: form.app_name || "QYLOT",
        overtime_alert_threshold: parseFloat(form.overtime_alert_threshold ?? 30) || 30,
        notifications: form.notifications || {},
        dashboard_widgets: form.dashboard_widgets || {},
        sale_status_order: Array.isArray(form.sale_status_order) && form.sale_status_order.length > 0 ? form.sale_status_order : null,
        prospect_smic_threshold: parseInt(form.prospect_smic_threshold ?? 3, 10) || 3,
        prospect_smic_amount: parseFloat(form.prospect_smic_amount ?? 1867) || 0,
        prospect_mgr_goal_sales: parseInt(form.prospect_mgr_goal_sales ?? 12, 10) || 12,
        prospect_mgr_rate_below: parseFloat(form.prospect_mgr_rate_below ?? 1) || 0,
        prospect_mgr_rate_above: parseFloat(form.prospect_mgr_rate_above ?? 2) || 0,
        prospect_mgr_base_amount: parseFloat(form.prospect_mgr_base_amount ?? 2329.97) || 0,
        prospect_mgr_bonuses: cleanMgrBonuses(form.prospect_mgr_bonuses),
      });
      toast.success("Paramètres enregistrés");
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setSaving(false); }
  };

  const setNotif = (key, val) => {
    setForm((prev) => ({ ...prev, notifications: { ...(prev.notifications || {}), [key]: !!val } }));
  };

  const setWidget = (key, val) => {
    setForm((prev) => ({ ...prev, dashboard_widgets: { ...(prev.dashboard_widgets || {}), [key]: !!val } }));
  };

  // Reorder statuses via native HTML5 drag-and-drop (no extra dep)
  const currentOrder = React.useMemo(() => {
    const list = Array.isArray(form.sale_status_order) && form.sale_status_order.length > 0
      ? orderStatuses(form.sale_status_order)
      : SALE_STATUSES;
    return list.map((s) => s.value);
  }, [form.sale_status_order]);
  const [dragIdx, setDragIdx] = React.useState(null);
  const onDragStart = (i) => setDragIdx(i);
  const onDragOver = (e) => { e.preventDefault(); };
  const onDrop = (i) => {
    if (dragIdx === null || dragIdx === i) return;
    const next = [...currentOrder];
    const [moved] = next.splice(dragIdx, 1);
    next.splice(i, 0, moved);
    setForm((prev) => ({ ...prev, sale_status_order: next }));
    setDragIdx(null);
  };
  const move = (i, delta) => {
    const j = i + delta;
    if (j < 0 || j >= currentOrder.length) return;
    const next = [...currentOrder];
    [next[i], next[j]] = [next[j], next[i]];
    setForm((prev) => ({ ...prev, sale_status_order: next }));
  };
  const resetOrder = () => setForm((prev) => ({ ...prev, sale_status_order: null }));

  const reset = async () => {
    if (!window.confirm("Réinitialiser aux valeurs par défaut ?")) return;
    setSaving(true);
    try {
      await update({ theme_primary: "#0f172a", theme_accent: "#6366f1", font_family: "Inter", logo: "", app_name: "KEYLOT" });
      toast.success("Paramètres réinitialisés");
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setSaving(false); }
  };

  const uploadLogo = async (files) => {
    if (!files || !files[0]) return;
    try {
      const b64 = await fileToBase64(files[0]);
      setForm({ ...form, logo: b64 });
      toast.success("Logo prêt — cliquez sur Enregistrer pour appliquer");
    } catch (err) { toast.error("Erreur d'upload"); }
    finally { if (fileRef.current) fileRef.current.value = ""; }
  };

  return (
    <div className="p-4 md:p-8 max-w-[1100px]">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="overline">Personnalisation</p>
          <h1 className="font-display text-4xl font-semibold tracking-tight">Paramètres</h1>
          <p className="text-sm text-slate-500 mt-2">Ajustez l'apparence de l'application au goût de votre équipe.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={reset} disabled={saving} data-testid="settings-reset-btn"><RotateCcw size={14} className="mr-2" />Réinitialiser</Button>
          <Button onClick={save} disabled={saving} data-testid="settings-save-btn"><Save size={14} className="mr-2" />{saving ? "Enregistrement…" : "Enregistrer"}</Button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Identity */}
        <Card className="border-slate-200 shadow-sm p-6">
          <div className="flex items-center gap-2 mb-4">
            <ImageIcon size={16} className="text-slate-500" />
            <p className="font-display text-lg font-semibold">Identité</p>
          </div>
          <div className="space-y-4">
            <div>
              <Label>Nom de la société / application</Label>
              <Input value={form.app_name || ""} onChange={(e) => setForm({ ...form, app_name: e.target.value })} placeholder="KEYLOT" data-testid="settings-appname" />
              <p className="text-xs text-slate-500 mt-1.5">S'affiche en haut de la barre latérale et sur la page de connexion.</p>
            </div>
            <div>
              <Label>Logo</Label>
              <div className="flex items-center gap-3 mt-1.5">
                <div className="h-16 w-16 rounded-lg border border-slate-200 bg-slate-50 grid place-items-center overflow-hidden">
                  {form.logo ? <img src={form.logo} alt="logo" className="h-full w-full object-contain" /> : <ImageIcon size={22} className="text-slate-300" />}
                </div>
                <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => uploadLogo(e.target.files)} data-testid="settings-logo-input" />
                <Button variant="outline" size="sm" onClick={() => fileRef.current?.click()} data-testid="settings-logo-btn">Choisir un logo</Button>
                {form.logo && <Button variant="ghost" size="sm" onClick={() => setForm({ ...form, logo: "" })} className="text-red-600">Retirer</Button>}
              </div>
              <p className="text-xs text-slate-500 mt-1.5">PNG conseillé, fond transparent. Redimensionné automatiquement.</p>
            </div>
          </div>
        </Card>

        {/* Typography */}
        <Card className="border-slate-200 shadow-sm p-6">
          <div className="flex items-center gap-2 mb-4">
            <Type size={16} className="text-slate-500" />
            <p className="font-display text-lg font-semibold">Typographie</p>
          </div>
          <div className="space-y-4">
            <div>
              <Label>Police d'écriture</Label>
              <Select value={form.font_family} onValueChange={(v) => setForm({ ...form, font_family: v })}>
                <SelectTrigger data-testid="settings-font"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {AVAILABLE_FONTS.map((f) => (<SelectItem key={f} value={f} style={{ fontFamily: `"${f}"` }}>{f}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50/50 p-4">
              <p className="text-xs uppercase tracking-widest text-slate-500 mb-1">Aperçu</p>
              <p className="text-2xl font-semibold" style={{ fontFamily: `"${form.font_family}", sans-serif` }}>Bonjour, {form.app_name || "KEYLOT"} 👋</p>
              <p className="text-sm text-slate-600 mt-1" style={{ fontFamily: `"${form.font_family}", sans-serif` }}>Le meilleur outil pour vos ventes et chantiers.</p>
            </div>
          </div>
        </Card>

        {/* Colors */}
        <Card className="border-slate-200 shadow-sm p-6 lg:col-span-2">
          <div className="flex items-center gap-2 mb-4">
            <Palette size={16} className="text-slate-500" />
            <p className="font-display text-lg font-semibold">Couleurs</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <Label>Couleur principale (fond sidebar, boutons)</Label>
              <div className="flex items-center gap-2 mt-2">
                <input type="color" value={form.theme_primary} onChange={(e) => setForm({ ...form, theme_primary: e.target.value })} className="h-10 w-14 rounded border border-slate-200" data-testid="settings-color-primary" />
                <Input value={form.theme_primary} onChange={(e) => setForm({ ...form, theme_primary: e.target.value })} className="h-10 font-mono text-sm" />
              </div>
              <div className="flex flex-wrap gap-1.5 mt-2">
                {PRESET_PRIMARY.map((c) => (
                  <button key={c} onClick={() => setForm({ ...form, theme_primary: c })} className="h-6 w-6 rounded-full border-2 border-white shadow ring-1 ring-slate-200" style={{ background: c }} aria-label={c} data-testid={`preset-primary-${c}`} />
                ))}
              </div>
            </div>
            <div>
              <Label>Couleur d'accent (jauge, badges)</Label>
              <div className="flex items-center gap-2 mt-2">
                <input type="color" value={form.theme_accent} onChange={(e) => setForm({ ...form, theme_accent: e.target.value })} className="h-10 w-14 rounded border border-slate-200" data-testid="settings-color-accent" />
                <Input value={form.theme_accent} onChange={(e) => setForm({ ...form, theme_accent: e.target.value })} className="h-10 font-mono text-sm" />
              </div>
              <div className="flex flex-wrap gap-1.5 mt-2">
                {PRESET_ACCENT.map((c) => (
                  <button key={c} onClick={() => setForm({ ...form, theme_accent: c })} className="h-6 w-6 rounded-full border-2 border-white shadow ring-1 ring-slate-200" style={{ background: c }} aria-label={c} data-testid={`preset-accent-${c}`} />
                ))}
              </div>
            </div>
          </div>

          {/* Live preview strip */}
          <div className="mt-6 rounded-lg p-4 border" style={{ background: form.theme_primary, color: "white" }}>
            <p className="text-xs uppercase tracking-widest opacity-80 mb-1">Aperçu couleurs</p>
            <div className="flex items-center gap-3">
              <span className="font-display text-xl font-semibold">{form.app_name || "KEYLOT"}</span>
              <span className="px-2.5 py-1 rounded-full text-xs font-semibold" style={{ background: form.theme_accent }}>Accent</span>
              <button className="ml-auto px-3 py-1.5 rounded-md text-sm font-medium" style={{ background: form.theme_accent }}>Bouton</button>
            </div>
          </div>
        </Card>

        {/* Notifications */}
        <Card className="border-slate-200 shadow-sm p-6 lg:col-span-2" data-testid="settings-notifications">
          <div className="flex items-center gap-2 mb-4">
            <Bell size={16} className="text-slate-500" />
            <p className="font-display text-lg font-semibold">Notifications</p>
            <span className="ml-auto text-xs text-slate-500">Optionnelles — désactivées par défaut</span>
          </div>
          <p className="text-sm text-slate-600 mb-4">Activez ou désactivez chaque catégorie. Les notifications apparaissent dans la cloche en haut de l'application, uniquement pour les rôles concernés.</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[
              { key: "new_sales", label: "Nouvelles ventes", desc: "Prévient les admins à chaque vente enregistrée." },
              { key: "objectives", label: "Progression des objectifs", desc: "Alertes 50 / 75 / 90 / 100 % de l'objectif mensuel." },
              { key: "planning", label: "Modifications de planning", desc: "Changement d'affectation ou de date d'un chantier." },
              { key: "overtime", label: "Heures supplémentaires", desc: "Nouvelle déclaration à valider (admin & responsable)." },
              { key: "project_alerts", label: "Alertes chantier", desc: "Chantiers à planifier ou en retard." },
              { key: "chantier_started", label: "Email : chantier programmé", desc: "Un email est envoyé aux techniciens/sous-traitants dès qu'un chantier passe en « PROG »." },
              { key: "chantier_confirmed", label: "Email + notification : chantier confirmé", desc: "Un email et une notification cloche sont envoyés aux techniciens/sous-traitants dès qu'un chantier est confirmé (bouton vert)." },
              { key: "chantier_terminated", label: "Email : chantier terminé", desc: "Un email est envoyé au commercial concerné ET aux administrateurs / responsables dès qu'un technicien valide le chantier terminé (à encaisser)." },
              { key: "attente_14j_jourj_notif", label: "Notification automatique au bout de 14 jours", desc: "Envoie une notification cloche bien visible au(x) commercial(aux) et aux admins dès qu'une vente en « attente 14 jours » atteint le Jour J. Ne modifie pas le statut de la vente." },
            ].map((c) => (
              <label key={c.key} className="flex items-start gap-3 rounded-lg border border-slate-200 p-3 cursor-pointer hover:bg-slate-50/60" data-testid={`notif-toggle-${c.key}`}>
                <Switch checked={!!(form.notifications || {})[c.key]} onCheckedChange={(v) => setNotif(c.key, v)} />
                <div className="flex-1">
                  <p className="text-sm font-semibold text-slate-900">{c.label}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{c.desc}</p>
                </div>
              </label>
            ))}
          </div>
        </Card>

        {/* Seuil d'alerte heures supplémentaires */}
        <Card id="overtime-threshold" className="border-slate-200 shadow-sm p-6 lg:col-span-2 transition-all" data-testid="settings-overtime-threshold">
          <div className="flex items-center gap-2 mb-4">
            <AlarmClock size={16} className="text-slate-500" />
            <p className="font-display text-lg font-semibold">Seuil d'alerte — Heures sup</p>
            <span className="ml-auto text-xs text-slate-500">Alerte rouge sur la page Heures sup</span>
          </div>
          <p className="text-sm text-slate-600 mb-4">
            Nombre d'heures supplémentaires par mois au-dessus duquel un bandeau rouge s'affiche. Le <b>seuil global</b> s'applique à tous les techniciens ; vous pouvez ensuite <b>personnaliser</b> le seuil pour chacun.
          </p>
          <div className="flex items-center gap-3 max-w-sm">
            <Input
              type="number"
              min="0"
              step="1"
              value={form.overtime_alert_threshold ?? 30}
              onChange={(e) => setForm({ ...form, overtime_alert_threshold: e.target.value })}
              className="h-10 max-w-[120px] text-center font-mono text-base"
              data-testid="overtime-threshold-input"
            />
            <span className="text-sm text-slate-600">heures / mois (global)</span>
          </div>
          <p className="text-[11px] text-slate-400 mt-2">Défaut : 30 h/mois. Cliquez sur « Enregistrer » en haut pour appliquer.</p>

          {/* iter116 : Seuils par technicien */}
          <div className="mt-6 pt-4 border-t border-slate-200">
            <p className="text-sm font-semibold text-slate-800 mb-1">Seuil personnalisé par technicien</p>
            <p className="text-xs text-slate-500 mb-3">Laisser vide pour appliquer le seuil global ({form.overtime_alert_threshold ?? 30} h/mois).</p>
            <PerTechThresholdList globalThreshold={form.overtime_alert_threshold ?? 30} />
          </div>
        </Card>

        {/* Rémunération prospecteurs */}
        <Card className="border-slate-200 shadow-sm p-6 lg:col-span-2" data-testid="settings-prospect-pay">
          <div className="flex items-center gap-2 mb-4">
            <AlarmClock size={16} className="text-slate-500" />
            <p className="font-display text-lg font-semibold">Rémunération des prospecteurs</p>
          </div>
          <p className="text-sm text-slate-600 mb-4">
            Le <b>salaire de base</b> est acquis dès la 1re vente du mois et couvre les premières ventes. À partir de la vente suivante, la commission fixe saisie sur chaque vente s'ajoute.
          </p>
          <div className="flex flex-wrap items-center gap-3 text-sm text-slate-700">
            <span>De 1 à</span>
            <Input type="number" min="1" step="1" value={form.prospect_smic_threshold ?? 3}
              onChange={(e) => setForm({ ...form, prospect_smic_threshold: e.target.value })}
              className="h-10 w-20 text-center font-mono" data-testid="prospect-smic-threshold-input" />
            <span>ventes / mois =</span>
            <Input type="number" min="0" step="1" value={form.prospect_smic_amount ?? 1867}
              onChange={(e) => setForm({ ...form, prospect_smic_amount: e.target.value })}
              className="h-10 w-28 text-center font-mono" data-testid="prospect-smic-amount-input" />
            <span>€ de salaire de base (SMIC)</span>
          </div>
          <p className="text-[11px] text-slate-400 mt-2">Préréglage : de 1 à 3 ventes = 1 867 €, commissions à partir de la 4e vente. Cliquez sur « Enregistrer » en haut pour appliquer.</p>
          <div className="border-t border-slate-100 mt-5 pt-5">
            <p className="text-sm font-semibold text-slate-800 mb-2">Rémunération du responsable prospection</p>
            <div className="flex flex-wrap items-center gap-3 text-sm text-slate-700 mb-3">
              <span>Salaire de base :</span>
              <Input type="number" min="0" step="0.01" value={form.prospect_mgr_base_amount ?? 2329.97}
                onChange={(e) => setForm({ ...form, prospect_mgr_base_amount: e.target.value })}
                className="h-10 w-32 text-center font-mono" data-testid="prospect-mgr-base-input" />
              <span>€ brut / mois</span>
            </div>
            <div className="flex flex-wrap items-center gap-3 text-sm text-slate-700">
              <span>Objectif :</span>
              <Input type="number" min="1" step="1" value={form.prospect_mgr_goal_sales ?? 12}
                onChange={(e) => setForm({ ...form, prospect_mgr_goal_sales: e.target.value })}
                className="h-10 w-20 text-center font-mono" data-testid="prospect-mgr-goal-input" />
              <span>ventes / mois — non atteint :</span>
              <Input type="number" min="0" step="0.1" value={form.prospect_mgr_rate_below ?? 1}
                onChange={(e) => setForm({ ...form, prospect_mgr_rate_below: e.target.value })}
                className="h-10 w-20 text-center font-mono" data-testid="prospect-mgr-rate-below-input" />
              <span>% — atteint :</span>
              <Input type="number" min="0" step="0.1" value={form.prospect_mgr_rate_above ?? 2}
                onChange={(e) => setForm({ ...form, prospect_mgr_rate_above: e.target.value })}
                className="h-10 w-20 text-center font-mono" data-testid="prospect-mgr-rate-above-input" />
              <span>% du CA des prospecteurs</span>
            </div>
            <p className="text-[11px] text-slate-400 mt-2">Préréglage : salaire de base 2 329,97 € brut, objectif 12 ventes / mois, 1 % si non atteint, 2 % si atteint.</p>
          </div>
          <ProspectMgrBonusesEditor value={form.prospect_mgr_bonuses} onChange={(v) => setForm({ ...form, prospect_mgr_bonuses: v })} />
        </Card>

        {/* Layout customization — Dashboard widgets */}
        <Card className="border-slate-200 shadow-sm p-6 lg:col-span-2" data-testid="settings-dashboard-widgets">
          <div className="flex items-center gap-2 mb-4">
            <LayoutGrid size={16} className="text-slate-500" />
            <p className="font-display text-lg font-semibold">Blocs du tableau de bord</p>
            <span className="ml-auto text-xs text-slate-500">Affichez ou masquez chaque bloc</span>
          </div>
          <p className="text-sm text-slate-600 mb-4">Cochez uniquement les blocs que vous souhaitez voir. Le choix est enregistré et suit la société.</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {[
              { key: "ca_hero", label: "Chiffre d'affaires signé (hero)", desc: "La grande carte CA + objectif en haut." },
              { key: "stats", label: "KPIs (Ventes, Clients, À planifier, En cours)", desc: "La rangée de 4 stats." },
              { key: "alerts", label: "À traiter", desc: "Alertes chantiers / commissions." },
              { key: "commissions", label: "Commissions du mois", desc: "Encart lien vers /commissions." },
              { key: "overtime", label: "Heures sup à valider", desc: "Encart heures sup en attente." },
              { key: "events", label: "Événements à venir", desc: "Événements marqués pour le dashboard." },
              { key: "ranking", label: "Classement commercial", desc: "Le podium des commerciaux." },
              { key: "recent_sales", label: "Ventes récentes", desc: "La liste des dernières ventes." },
            ].map((c) => (
              <label key={c.key} className="flex items-start gap-3 rounded-lg border border-slate-200 p-3 cursor-pointer hover:bg-slate-50/60" data-testid={`widget-toggle-${c.key}`}>
                <Switch checked={(form.dashboard_widgets || {})[c.key] !== false} onCheckedChange={(v) => setWidget(c.key, v)} />
                <div className="flex-1">
                  <p className="text-sm font-semibold text-slate-900">{c.label}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{c.desc}</p>
                </div>
              </label>
            ))}
          </div>
        </Card>

        {/* Statut de vente — order */}
        <Card className="border-slate-200 shadow-sm p-6 lg:col-span-2" data-testid="settings-status-order">          <div className="flex items-center gap-2 mb-4">
            <GripVertical size={16} className="text-slate-500" />
            <p className="font-display text-lg font-semibold">Ordre des statuts de vente</p>
            <span className="ml-auto text-xs text-slate-500">Glissez-déposez pour réorganiser</span>
          </div>
          <p className="text-sm text-slate-600 mb-4">Cet ordre s'applique partout où les statuts apparaissent (liste Ventes, sélecteurs, menus). Il est propre à votre société.</p>
          <div className="space-y-2 max-w-md">
            {currentOrder.map((v, i) => {
              const s = SALE_STATUSES.find((x) => x.value === v);
              if (!s) return null;
              return (
                <div
                  key={v}
                  draggable
                  onDragStart={() => onDragStart(i)}
                  onDragOver={onDragOver}
                  onDrop={() => onDrop(i)}
                  className={`flex items-center gap-3 rounded-lg border p-2.5 bg-white ${dragIdx === i ? "opacity-40 border-slate-400" : "border-slate-200"} cursor-move`}
                  data-testid={`status-row-${v}`}
                >
                  <GripVertical size={14} className="text-slate-400 shrink-0" />
                  <span className={`inline-block h-3 w-3 rounded-full shrink-0 ${s.cls.split(" ")[0]}`} />
                  <span className="text-sm font-medium text-slate-900 flex-1">{s.label}</span>
                  <div className="flex gap-1 shrink-0">
                    <button type="button" onClick={() => move(i, -1)} disabled={i === 0} className="h-7 w-7 rounded-md text-slate-500 hover:text-slate-900 hover:bg-slate-100 disabled:opacity-30" aria-label="Monter" data-testid={`status-up-${v}`}>↑</button>
                    <button type="button" onClick={() => move(i, 1)} disabled={i === currentOrder.length - 1} className="h-7 w-7 rounded-md text-slate-500 hover:text-slate-900 hover:bg-slate-100 disabled:opacity-30" aria-label="Descendre" data-testid={`status-down-${v}`}>↓</button>
                  </div>
                </div>
              );
            })}
          </div>
          <button type="button" onClick={resetOrder} className="mt-3 text-xs text-slate-500 hover:text-slate-900" data-testid="status-reset">Réinitialiser à l'ordre par défaut</button>
          <div className="mt-4 pt-3 border-t border-slate-200 flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setStatusManagerOpen(true)} data-testid="settings-manage-statuses-btn">
              <Pencil size={13} className="mr-1.5" /> Ajouter · Renommer · Couleur · Supprimer
            </Button>
            <span className="text-xs text-slate-500">Gestion complète des statuts (crayon + croix)</span>
          </div>
        </Card>

        {/* Primes par palier CA */}
        <Card className="border-slate-200 shadow-sm p-6 lg:col-span-2" data-testid="settings-bonuses">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp size={16} className="text-slate-500" />
            <p className="font-display text-lg font-semibold">Primes par palier CA</p>
            <span className="ml-auto text-xs text-slate-500">{bonusCount > 0 ? `${bonusCount} palier${bonusCount > 1 ? "s" : ""} configuré${bonusCount > 1 ? "s" : ""}` : "Aucun palier"}</span>
          </div>
          <p className="text-sm text-slate-600 mb-4">
            Configurez des paliers de chiffre d'affaires qui déclenchent une prime pour un ou tous vos commerciaux (mensuel, trimestriel, annuel ou global). La progression s'affiche automatiquement sur la page Commissions.
          </p>
          <Button variant="outline" onClick={() => setBonusesOpen(true)} data-testid="settings-bonuses-open">
            <TrendingUp size={14} className="mr-2" /> Gérer les paliers
          </Button>
        </Card>
      </div>
      <BonusesDialog open={bonusesOpen} onOpenChange={setBonusesOpen} onChanged={() => { /* count refreshes on close via effect */ }} />
      <StatusManagerDialog open={statusManagerOpen} onOpenChange={setStatusManagerOpen} onSaved={() => { window.dispatchEvent(new Event("kylot:settings-updated")); }} />
    </div>
  );
}
