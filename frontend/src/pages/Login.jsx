import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { useSettings } from "@/contexts/SettingsContext";
import { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { ArrowUpRight, Compass, Eye, EyeOff, ShieldCheck, LockKeyhole } from "lucide-react";
import IntroSplash from "@/components/IntroSplash";

export default function Login() {
  const { login, verifyMfa } = useAuth();
  const { settings } = useSettings();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [mfaChallenge, setMfaChallenge] = useState("");
  const [mfaCode, setMfaCode] = useState("");
  const [error, setError] = useState(() => {
    try {
      const p = new URLSearchParams(window.location.search);
      if (p.get("expired") === "1") return "Votre session a expiré. Merci de vous reconnecter.";
    } catch (_) {}
    return "";
  });

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const result = await login(email, password);
      if (result?.mfa_required) {
        setMfaChallenge(result.challenge);
        setMfaCode("");
        toast.info("Saisissez le code de votre application d'authentification.");
        return;
      }
      toast.success("Bienvenue !");
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const submitMfa = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await verifyMfa(mfaChallenge, mfaCode);
      toast.success("Bienvenue !");
    } catch (err) {
      setError(formatApiError(err));
    } finally {
      setLoading(false);
    }
  };

  const appName = settings.app_name || "Qylot";

  return (
    <div className="min-h-screen bg-[#F5F7FA] text-[#111827]" data-testid="login-page">
      <IntroSplash />
      <div className="grid min-h-screen lg:grid-cols-[1.08fr_.92fr]">
        {/* Brand panel */}
        <section className="relative hidden overflow-hidden bg-[#111827] px-12 py-12 text-[#F5F7FA] lg:flex lg:flex-col xl:px-20">
          <div className="pointer-events-none absolute inset-0 opacity-[.16]" style={{ backgroundImage: "linear-gradient(rgba(247,243,233,.22) 1px, transparent 1px), linear-gradient(90deg, rgba(247,243,233,.22) 1px, transparent 1px)", backgroundSize: "72px 72px" }} />
          <div className="pointer-events-none absolute -right-40 top-1/3 h-[540px] w-[540px] rounded-full border border-[#5271FF]/25" />
          <div className="pointer-events-none absolute -right-24 top-1/3 h-[380px] w-[380px] rounded-full border border-[#5271FF]/15" />

          <div className="relative flex items-center gap-3">
            <div className="grid h-12 w-12 place-items-center overflow-visible" data-testid="login-logo">
              {settings.logo ? <img src={settings.logo} alt="logo" className="h-full w-full object-contain" /> : <img src="/brand/qylot-logo-nuit-azur.png" alt="Qylot" className="h-full w-full object-contain" />}
            </div>
            <div>
              <div className="font-display text-[22px] font-semibold leading-none tracking-[-.02em]">{appName}</div>
              <div className="mt-1 text-[9px] uppercase tracking-[.22em] text-white/40">Chantiers & croissance</div>
            </div>
          </div>

          <div className="relative my-auto max-w-[570px] py-12">
            <h1 className="font-display text-[46px] font-semibold leading-[.98] tracking-[-.055em] xl:text-[58px]">
              Vos ventes.<br />Vos chantiers.<br /><span className="text-[#5271FF]">Votre équipe.</span>
            </h1>
            <p className="mt-6 max-w-[430px] text-[15px] leading-relaxed text-white/55">
              Du premier contact à la marge validée.
            </p>
            <div className="qy-login-timeline mt-9 rounded-2xl border border-white/10 bg-white/[.045] p-4 backdrop-blur-sm" data-testid="login-flow-preview">
              <p className="text-[9px] font-semibold uppercase tracking-[.18em] text-white/40">Le parcours Qylot</p>
              <ol className="relative mt-3 space-y-3">
                <span className="pointer-events-none absolute bottom-2 left-[9px] top-2 w-px bg-white/10" aria-hidden="true" />
                {[
                  ["01", "Vente signée"],
                  ["02", "Chantier planifié"],
                  ["03", "Équipe affectée"],
                  ["04", "Marge suivie"],
                ].map(([num, title], i) => (
                  <li key={num} className="relative flex items-start gap-3" data-testid={`login-flow-step-${i + 1}`}>
                    <span className={`relative z-10 grid h-5 w-5 shrink-0 place-items-center rounded-full border text-[9px] font-semibold ${i === 3 ? "border-emerald-400/40 bg-emerald-400/15 text-emerald-300" : "border-white/20 bg-[#111827] text-white/60"}`}>{num}</span>
                    <p className={`text-[11px] font-medium ${i === 3 ? "text-emerald-200" : "text-white/80"}`}>{title}</p>
                  </li>
                ))}
              </ol>
            </div>
          </div>

          <div className="relative flex items-center justify-between border-t border-white/10 pt-5 text-[10px] uppercase tracking-[.16em] text-white/30">
            <span>Version 2026</span>
            <span className="inline-flex items-center gap-1.5"><LockKeyhole size={11} /> Données sécurisées</span>
          </div>
        </section>

        {/* Form panel */}
        <section className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-[#F7F9FC] px-5 py-10 sm:px-10 lg:px-14 xl:px-20">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(600px_300px_at_80%_10%,rgba(82,113,255,.08),transparent_70%)]" />
          <div className="pointer-events-none absolute inset-0 opacity-[.35]" style={{ backgroundImage: "linear-gradient(rgba(17,24,39,.04) 1px, transparent 1px), linear-gradient(90deg, rgba(17,24,39,.04) 1px, transparent 1px)", backgroundSize: "56px 56px" }} />
          <div className="mb-10 flex items-center gap-2.5 lg:hidden">
            <div className="grid h-10 w-10 place-items-center overflow-visible">
              {settings.logo ? <img src={settings.logo} alt="logo" className="h-full w-full object-contain" /> : <img src="/brand/qylot-logo-nuit-azur.png" alt="Qylot" className="h-full w-full object-contain" />}
            </div>
            <span className="font-display text-lg font-semibold tracking-[-.02em]">{appName}</span>
          </div>

          <div className="relative w-full max-w-[450px] rounded-2xl border border-[#E2E8F0] bg-white/90 p-5 shadow-[0_28px_80px_rgba(17,24,39,.10)] backdrop-blur-sm sm:p-8">
            <div className="mb-7 flex items-center justify-between gap-3">
              <p className="text-[10px] font-semibold uppercase tracking-[.2em] text-[#5271FF]">{mfaChallenge ? "Vérification" : "Connexion"}</p>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-[#DDE3EC] bg-[#F8FAFC] px-2.5 py-1 text-[10px] font-medium text-[#667085]">
                <ShieldCheck size={12} className="text-[#5271FF]" /> Accès sécurisé
              </span>
            </div>
            <div className="mb-8">
              <h2 className="font-display text-[32px] font-semibold leading-tight tracking-[-.04em] text-[#111827] sm:text-[38px]">
                {mfaChallenge ? "Un dernier contrôle." : "Connectez-vous."}
              </h2>
              <p className="mt-3 text-[13px] leading-relaxed text-[#667085]">
                {mfaChallenge ? "Saisissez le code à 6 chiffres de votre application d'authentification." : "Accédez à votre espace de travail."}
              </p>
            </div>

            {mfaChallenge ? (
              <form onSubmit={submitMfa} className="space-y-5" data-testid="login-mfa-form">
                <div className="space-y-1.5">
                  <Label htmlFor="mfa-code" className="text-[12px] font-medium text-[#344054]">Code d'authentification</Label>
                  <Input
                    id="mfa-code"
                    inputMode="text"
                    autoComplete="one-time-code"
                    autoFocus
                    required
                    minLength={6}
                    maxLength={32}
                    value={mfaCode}
                    onChange={(e) => setMfaCode(e.target.value)}
                    data-testid="login-mfa-code-input"
                    placeholder="123456 ou code de secours"
                    className="qy-login-field h-12 rounded-xl border-[#DDE3EC] bg-white text-[15px] shadow-none focus-visible:ring-[#5271FF]"
                  />
                </div>
                {error && <ErrorBox error={error} />}
                <Button type="submit" disabled={loading} className="h-12 w-full rounded-xl bg-[#5271FF] text-[14px] font-semibold text-white hover:bg-[#3B56D9]" data-testid="login-mfa-submit-btn">
                  {loading ? "Vérification…" : "Valider le code"}
                </Button>
                <button type="button" className="w-full text-xs font-medium text-[#667085] underline underline-offset-4 hover:text-[#111827]" onClick={() => { setMfaChallenge(""); setMfaCode(""); setError(""); }}>
                  Revenir à la connexion
                </button>
              </form>
            ) : (
              <form onSubmit={submit} className="space-y-5" data-testid="login-form">
                <div className="space-y-1.5">
                  <Label htmlFor="email" className="text-[12px] font-medium text-[#344054]">Email professionnel</Label>
                  <Input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} data-testid="login-email-input" placeholder="vous@entreprise.fr" className="qy-login-field h-12 rounded-xl border-[#DDE3EC] bg-white text-[15px] shadow-none focus-visible:ring-[#5271FF]" />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="password" className="text-[12px] font-medium text-[#344054]">Mot de passe</Label>
                  <div className="relative">
                    <Input id="password" type={showPassword ? "text" : "password"} required value={password} onChange={(e) => setPassword(e.target.value)} data-testid="login-password-input" placeholder="••••••••" className="qy-login-field h-12 rounded-xl border-[#DDE3EC] bg-white pr-12 text-[15px] shadow-none focus-visible:ring-[#5271FF]" />
                    <button type="button" onClick={() => setShowPassword((v) => !v)} aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"} className="absolute right-1.5 top-1/2 grid h-9 w-9 -translate-y-1/2 place-items-center rounded-lg text-[#667085] hover:bg-[#F2F4F7] hover:text-[#111827]" data-testid="login-password-toggle">
                      {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                </div>
                {error && <ErrorBox error={error} />}
                <div className="flex justify-end">
                  <Link to="/forgot-password" className="text-xs font-medium text-[#5271FF] underline underline-offset-4 hover:text-[#3B56D9]">Mot de passe oublié ?</Link>
                </div>
                <Button type="submit" disabled={loading} className="h-12 w-full rounded-xl bg-[#5271FF] text-[14px] font-semibold text-white hover:bg-[#3B56D9]" data-testid="login-submit-btn">
                  {loading ? "Connexion…" : <span className="flex items-center gap-2">Se connecter <ArrowUpRight size={16} /></span>}
                </Button>
              </form>
            )}

            <div className="mt-8 flex items-start gap-3 rounded-xl border border-[#DDE3EC] bg-white/50 p-4">
              <Compass size={17} className="mt-0.5 shrink-0 text-[#5271FF]" />
              <p className="text-[11px] leading-relaxed text-[#667085]">
                Un problème d’accès ? Contactez votre administrateur.
              </p>
            </div>
          </div>

          <div className="mt-10 flex items-center justify-between gap-4 text-[10px] text-[#98a2b3] lg:absolute lg:inset-x-14 lg:bottom-8 lg:mt-0 xl:inset-x-20">
            <span>© 2026 {appName}</span>
            <span>Connexion sécurisée</span>
          </div>
        </section>
      </div>
    </div>
  );
}

function ErrorBox({ error }) {
  return (
    <div className="rounded-xl border border-red-200 bg-red-50 px-3.5 py-3 text-sm text-red-700" data-testid="login-error" role="alert">
      {error}
    </div>
  );
}
