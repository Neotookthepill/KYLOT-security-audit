import React, { useEffect, useState, useMemo } from "react";
import api, { formatApiError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Check, Users, Star, Loader2, ShieldCheck, Settings as SettingsIcon, Gift, Sparkles, AlertTriangle, Calendar, ArrowRight } from "lucide-react";
import { toast } from "sonner";

// iter167 — Nouvelle grille tarifaire simple :
//   1–6  utilisateurs → Essentiel  49 € HT / mois
//   7–12 utilisateurs → Équipe     89 € HT / mois
//   13–20 utilisateurs → Entreprise 149 € HT / mois
//   21+  utilisateurs → Entreprise 149 € + 10 € HT/mois par utilisateur au-delà de 20.
// Toutes les formules incluent 100 % des fonctionnalités.
const ALL_FEATURES = [
  "Toutes les fonctionnalités QYLOT incluses",
  "Gestion commerciale complète",
  "Gestion des techniciens & sous-traitants",
  "Planning des interventions",
  "Gestion des chantiers & photos",
  "Suivi des ventes & commissions",
  "Heures supplémentaires",
  "Tableaux de bord & rapports",
  "Exports CSV / PDF",
  "Statistiques avancées",
  "Rôles & permissions",
  "Assistant IA KIK'S",
  "Support prioritaire",
];

const PLANS = [
  { key: "essentiel", lookup_key: "keylot_essentiel_monthly", label: "Essentiel", price: 39, max: 3, range: "1 à 3 utilisateurs", tagline: "L'essentiel pour bien démarrer" },
  { key: "equipe", lookup_key: "keylot_equipe_monthly", label: "Équipe", price: 69, max: 8, range: "4 à 8 utilisateurs", popular: true, tagline: "Pour les équipes en pleine croissance" },
  { key: "entreprise", lookup_key: "keylot_entreprise_monthly", label: "Entreprise", price: 99, max: null, range: "9 à 15 utilisateurs", tagline: "Sans limite d'utilisateurs (+10 € HT/u au-delà de 15)" },
];

const fmtDate = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
};

const STATUS_LABELS = {
  trialing: { label: "Essai gratuit", cls: "bg-indigo-100 text-indigo-800", icon: Gift },
  active: { label: "Actif", cls: "bg-emerald-100 text-emerald-800", icon: ShieldCheck },
  past_due: { label: "Paiement en retard", cls: "bg-amber-100 text-amber-800", icon: AlertTriangle },
  suspended: { label: "Suspendu", cls: "bg-red-100 text-red-800", icon: AlertTriangle },
  canceled: { label: "Résilié", cls: "bg-slate-200 text-slate-700", icon: AlertTriangle },
  cancelled: { label: "Résilié", cls: "bg-slate-200 text-slate-700", icon: AlertTriangle },
  incomplete: { label: "En cours", cls: "bg-slate-100 text-slate-700", icon: Loader2 },
};

export default function Abonnement() {
  const [loadingKey, setLoadingKey] = useState(null);
  const [openingPortal, setOpeningPortal] = useState(false);
  const [mySub, setMySub] = useState(null);

  const loadSub = () => api.get("/subscription/me").then((r) => setMySub(r.data)).catch(() => {});
  useEffect(() => { loadSub(); }, []);

  const choosePlan = async (p) => {
    setLoadingKey(p.key);
    try {
      const { data } = await api.post("/payments/checkout", { lookup_key: p.lookup_key, origin_url: window.location.origin });
      window.location.href = data.checkout_url;
    } catch (err) { toast.error(formatApiError(err)); setLoadingKey(null); }
  };

  const openPortal = async () => {
    setOpeningPortal(true);
    try {
      const { data } = await api.post("/payments/portal", { return_url: window.location.origin + "/abonnement" });
      window.location.href = data.portal_url;
    } catch (err) { toast.error(formatApiError(err)); setOpeningPortal(false); }
  };

  const isActive = (p) => (mySub?.status === "active" || mySub?.status === "trialing") && mySub?.plan === p.lookup_key;
  const currentPlan = mySub?.plan ? PLANS.find((p) => p.lookup_key === mySub.plan) : null;
  const statusMeta = mySub?.status ? STATUS_LABELS[mySub.status] : null;
  const suggested = mySub?.suggested_plan ? PLANS.find((p) => p.lookup_key === mySub.suggested_plan) : null;
  const totalPrice = mySub?.pricing?.total_price;
  const extraUsers = mySub?.pricing?.extra_users || 0;
  const extraPrice = mySub?.pricing?.extra_price || 0;

  return (
    <div className="p-6 md:p-8 max-w-[1200px] mx-auto">
      <div className="mb-6 text-center">
        <p className="overline">Abonnement · Tarifs</p>
        <h1 className="font-display text-3xl md:text-4xl font-semibold tracking-tight">Un tarif simple, basé uniquement sur vos utilisateurs</h1>
        <p className="text-sm text-slate-600 mt-3 max-w-3xl mx-auto">
          Toutes les fonctionnalités QYLOT sont incluses dans chaque formule. Votre abonnement évolue simplement avec la taille de votre équipe.
        </p>
        <p className="text-xs text-slate-500 mt-2">Facturation mensuelle sans engagement · TVA en sus · Paiement sécurisé Stripe.</p>
      </div>

      {/* Trial banner */}
      {!currentPlan && (
        <div className="mb-6 rounded-2xl bg-gradient-to-r from-indigo-600 to-purple-600 text-white px-5 py-4 flex items-center gap-3 shadow-sm" data-testid="trial-banner">
          <div className="h-10 w-10 rounded-full bg-white/20 grid place-items-center shrink-0"><Sparkles size={18} /></div>
          <div className="flex-1">
            <p className="font-semibold text-lg">Essayez QYLOT gratuitement pendant 14 jours</p>
            <p className="text-sm text-white/85">Aucune facturation avant la fin de la période d'essai · Annulation à tout moment.</p>
          </div>
        </div>
      )}

      {/* Current subscription */}
      {mySub && currentPlan && (
        <Card className="p-5 md:p-6 border-slate-200 shadow-sm mb-8" data-testid="current-subscription">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="overline">Votre abonnement</p>
                {statusMeta && (<span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full ${statusMeta.cls}`}>{statusMeta.label.toUpperCase()}</span>)}
                {mySub.cancel_at_period_end && (<span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-red-100 text-red-800">RÉSILIATION PROGRAMMÉE</span>)}
              </div>
              <p className="font-display text-2xl font-semibold mt-1">
                {currentPlan.label}
                <span className="text-slate-500 font-normal text-lg"> — {totalPrice ?? currentPlan.price} € HT / mois</span>
              </p>
              {extraUsers > 0 && (
                <p className="text-xs text-slate-500 mt-1">
                  Base Entreprise {currentPlan.price} € + {extraUsers} utilisateur{extraUsers > 1 ? "s" : ""} supplémentaire{extraUsers > 1 ? "s" : ""} × 10 € = <strong>{extraPrice} €</strong> HT/mois d'extras.
                </p>
              )}
              <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
                <div><p className="text-slate-500">Début</p><p className="font-medium">{fmtDate(mySub.period_start)}</p></div>
                <div><p className="text-slate-500">{mySub.cancel_at_period_end ? "Résiliation le" : "Prochain renouvellement"}</p><p className="font-medium flex items-center gap-1"><Calendar size={12} />{fmtDate(mySub.period_end)}</p></div>
                {mySub.trial_end && <div><p className="text-slate-500">Fin d'essai</p><p className="font-medium text-indigo-700">{fmtDate(mySub.trial_end)}</p></div>}
                <div>
                  <p className="text-slate-500">Utilisateurs actifs</p>
                  <p className="font-medium">{mySub.active_users}</p>
                </div>
              </div>
              {/* Suggestion de bascule automatique */}
              {suggested && !mySub.suggested_matches_current && (
                <div className="mt-3 flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-900">
                  <AlertTriangle size={14} className="shrink-0" />
                  <span>
                    Votre équipe compte {mySub.active_users} utilisateurs — la formule adaptée est <strong>{suggested.label}</strong>.
                    Cliquez sur la carte pour basculer.
                  </span>
                </div>
              )}
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={openPortal} disabled={openingPortal} data-testid="manage-sub-btn">
                {openingPortal ? <Loader2 size={13} className="mr-1.5 animate-spin" /> : <SettingsIcon size={13} className="mr-1.5" />}
                Gérer mon abonnement
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Plans */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {PLANS.map((p) => {
          const active = isActive(p);
          const isSuggested = suggested?.lookup_key === p.lookup_key;
          return (
            <Card key={p.key} className={`relative p-6 border transition ${p.popular ? "border-slate-900 shadow-lg ring-2 ring-slate-900/10 md:scale-[1.03]" : "border-slate-200 shadow-sm"} ${active ? "ring-2 ring-emerald-400" : ""} ${isSuggested && !active ? "ring-2 ring-amber-400" : ""}`} data-testid={`plan-${p.key}`}>
              {p.popular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 flex items-center gap-1 px-3 py-1 rounded-full bg-slate-900 text-white text-xs font-semibold whitespace-nowrap">
                  <Star size={12} /> Le plus choisi
                </div>
              )}
              {isSuggested && !active && (
                <div className="absolute -top-3 right-4 flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-500 text-white text-[10px] font-semibold whitespace-nowrap">
                  Adapté à votre équipe
                </div>
              )}
              <div className="flex items-center gap-2 text-slate-500 text-xs uppercase tracking-widest font-semibold">
                <Users size={14} /> {p.label}
              </div>
              <p className="text-sm text-slate-600 mt-1">{p.tagline}</p>
              <div className="mt-3">
                <div className="flex items-baseline gap-1">
                  <span className="font-display text-5xl font-semibold">{p.price}</span>
                  <span className="font-display text-2xl">€</span>
                  <span className="text-sm text-slate-500 ml-1">HT / mois</span>
                </div>
                <p className="text-sm text-slate-700 font-medium mt-1">{p.range}</p>
                {p.key === "entreprise" && (
                  <p className="text-[11px] text-slate-500 mt-1 flex items-center gap-1">
                    <ArrowRight size={11} /> Puis <strong className="mx-0.5">+10 € HT / mois</strong> par utilisateur supplémentaire au-delà de 15.
                  </p>
                )}
              </div>
              <ul className="mt-5 space-y-2.5">
                {ALL_FEATURES.map((f) => (
                  <li key={f} className="flex items-start gap-2 text-sm text-slate-700">
                    <Check size={16} className="text-emerald-600 mt-0.5 shrink-0" /> {f}
                  </li>
                ))}
              </ul>
              <Button
                className="w-full mt-6 h-11"
                variant={active ? "outline" : (isSuggested ? "default" : (p.popular ? "default" : "outline"))}
                onClick={() => choosePlan(p)}
                disabled={active || loadingKey !== null}
                data-testid={`plan-${p.key}-btn`}
              >
                {loadingKey === p.key ? (<><Loader2 size={14} className="mr-1.5 animate-spin" /> Redirection…</>)
                  : active ? (<><Check size={14} className="mr-1.5" /> Plan actif</>)
                  : currentPlan ? "Changer pour ce plan"
                  : "Démarrer l'essai 14 jours"}
              </Button>
              {!active && !currentPlan && (
                <p className="text-[11px] text-center text-slate-500 mt-2">Aucune facturation les 14 premiers jours.</p>
              )}
            </Card>
          );
        })}
      </div>

      <p className="text-center text-xs text-slate-500 mt-8 max-w-2xl mx-auto">
        QYLOT est une solution destinée aux entreprises. Prix HT, la TVA au taux en vigueur est calculée à la commande.
        Vous pouvez changer, mettre en pause ou résilier votre abonnement à tout moment depuis « Gérer mon abonnement ».
        <br/><span className="text-slate-400">Aucun changement de formule ne modifie ou supprime vos données. En cas d'impayé, votre compte est simplement mis en pause — toutes vos données restent conservées.</span>
      </p>
    </div>
  );
}
