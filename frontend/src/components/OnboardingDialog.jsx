import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Building2, Users, ShieldCheck, Contact2, Target, Rocket, CheckCircle2, ArrowRight, ArrowLeft, SkipForward } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";

// iter183 — Onboarding « première utilisation UNIQUEMENT ».
// Persistance server-side (`users.onboarding_done`) → n'apparaît jamais à la
// reconnexion, quel que soit le navigateur / appareil.
// La condition d'ouverture n'est PLUS `localStorage` (per-browser) mais
// `user.onboarding_done === false` retourné par `/auth/me`.

const STEPS = [
  { key: "company", title: "Informations de l'entreprise", desc: "Complétez le nom, le logo, l'adresse et le SIRET de votre société.", icon: Building2, path: "/parametres", cta: "Ouvrir les paramètres" },
  { key: "users", title: "Ajouter vos premiers utilisateurs", desc: "Invitez vos commerciaux, techniciens et sous-traitants.", icon: Users, path: "/utilisateurs", cta: "Ajouter un utilisateur" },
  { key: "roles", title: "Définir les rôles et permissions", desc: "Choisissez qui voit quoi. Vous pourrez ajuster à tout moment.", icon: ShieldCheck, path: "/utilisateurs", cta: "Configurer les permissions" },
  { key: "clients", title: "Ajouter ou importer les clients", desc: "Importez un fichier CSV / XLSX ou saisissez vos premiers clients manuellement.", icon: Contact2, path: "/clients", cta: "Ajouter des clients" },
  { key: "objectif", title: "Définir l'objectif commercial mensuel", desc: "Fixez le CA cible pour piloter votre équipe.", icon: Target, path: "/parametres", cta: "Définir l'objectif" },
  { key: "first_sale", title: "Créer votre première vente ou chantier", desc: "Lancez votre activité opérationnelle avec QYLOT.", icon: Rocket, path: "/ventes", cta: "Créer une vente" },
];

export default function OnboardingDialog() {
  const { user, refreshUser } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  // Empêche de rappeler l'API plusieurs fois pendant le même cycle de vie.
  const [marked, setMarked] = useState(false);

  useEffect(() => {
    if (!user?.id) return;
    if (user.role !== "admin") return;
    // iter183 : SEULE condition d'affichage = flag serveur `onboarding_done === false`.
    // Un utilisateur qui a déjà vu l'onboarding NE le reverra JAMAIS, quel que soit
    // le navigateur, l'appareil, ou après clear cache.
    if (user.onboarding_done === true) return;
    const t = setTimeout(() => setOpen(true), 900);
    return () => clearTimeout(t);
  }, [user?.id, user?.role, user?.onboarding_done]);

  const total = STEPS.length;
  const pct = useMemo(() => Math.round(((step + 1) / total) * 100), [step, total]);
  const done = step >= total;

  const markDone = async () => {
    if (marked) return;
    setMarked(true);
    try { await api.post("/me/onboarding-complete"); } catch (_) {}
    try { await refreshUser?.(); } catch (_) {}
  };

  const finish = async () => {
    setOpen(false);
    await markDone();
  };
  const openStep = async (s) => {
    setOpen(false);
    await markDone();
    nav(s.path);
  };

  if (done) {
    return (
      <Dialog open={open} onOpenChange={(v) => { if (!v) finish(); else setOpen(v); }}>
        <DialogContent className="max-w-lg p-8 text-center" data-testid="onboarding-done">
          <DialogTitle className="sr-only">Onboarding terminé</DialogTitle>
          <div className="mx-auto h-14 w-14 rounded-full bg-emerald-100 text-emerald-700 grid place-items-center mb-3"><CheckCircle2 size={30} /></div>
          <h2 className="font-display text-2xl font-semibold">Votre espace QYLOT est prêt 🎉</h2>
          <p className="text-sm text-slate-600 mt-2">Vous pouvez à tout moment revenir sur ces étapes depuis les Paramètres.</p>
          <Button className="mt-6 w-full h-11" onClick={finish} data-testid="onboarding-close">Commencer à utiliser QYLOT</Button>
        </DialogContent>
      </Dialog>
    );
  }

  const s = STEPS[step];
  const Icon = s.icon;
  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) finish(); else setOpen(v); }}>
      <DialogContent className="max-w-lg p-0 overflow-hidden" data-testid="onboarding-dialog">
        <DialogTitle className="sr-only">Bienvenue sur QYLOT</DialogTitle>
        <div className="px-6 pt-5 pb-3 border-b border-slate-200">
          <div className="flex items-center justify-between">
            <p className="overline">Bienvenue sur QYLOT — étape {step + 1} / {total}</p>
            <button className="text-xs text-slate-500 hover:text-slate-700 flex items-center gap-1" onClick={finish} data-testid="onboarding-skip">Passer et fermer</button>
          </div>
          <Progress value={pct} className="mt-2 h-1.5" />
        </div>
        <div className="px-6 py-6">
          <div className="flex items-start gap-3">
            <div className="h-11 w-11 rounded-lg bg-indigo-50 text-indigo-700 grid place-items-center shrink-0"><Icon size={20} /></div>
            <div className="min-w-0">
              <h3 className="font-display text-lg font-semibold">{s.title}</h3>
              <p className="text-sm text-slate-600 mt-1">{s.desc}</p>
            </div>
          </div>
          <Button className="mt-5 w-full h-11" onClick={() => openStep(s)} data-testid={`onboarding-step-${s.key}-cta`}>
            {s.cta} <ArrowRight size={14} className="ml-1.5" />
          </Button>
        </div>
        <div className="px-6 py-3 border-t border-slate-200 bg-slate-50/60 flex items-center justify-between">
          <Button variant="ghost" size="sm" disabled={step === 0} onClick={() => setStep((v) => v - 1)} data-testid="onboarding-prev">
            <ArrowLeft size={13} className="mr-1" /> Précédent
          </Button>
          <Button variant="outline" size="sm" onClick={() => setStep((v) => v + 1)} data-testid="onboarding-next">
            {step === total - 1 ? "Terminer" : <>Passer <SkipForward size={13} className="ml-1" /></>}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
