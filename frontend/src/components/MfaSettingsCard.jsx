import React, { useState } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { ShieldCheck, KeyRound, Copy } from "lucide-react";

function formatSecret(secret) {
  return (secret || "").replace(/(.{4})/g, "$1 ").trim();
}

async function copyText(value) {
  try {
    await navigator.clipboard.writeText(value);
    toast.success("Copié");
  } catch (_) {
    toast.error("Copie impossible ; sélectionnez le texte manuellement.");
  }
}

export default function MfaSettingsCard() {
  const { user, refreshUser } = useAuth();
  const [password, setPassword] = useState("");
  const [setup, setSetup] = useState(null);
  const [code, setCode] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState([]);
  const [disablePassword, setDisablePassword] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const [busy, setBusy] = useState(false);

  if (!user || !["admin", "super_admin"].includes(user.role)) return null;
  const enabled = Boolean(user.mfa_enabled);

  const startSetup = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/auth/mfa/setup", { password });
      setSetup(data);
      setRecoveryCodes([]);
      setPassword("");
      toast.success("Scannez ou saisissez le secret dans votre application.");
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const confirmSetup = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/auth/mfa/confirm", { code });
      setRecoveryCodes(data.recovery_codes || []);
      setSetup(null);
      setCode("");
      await refreshUser();
      toast.success("Double authentification activée.");
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setBusy(true);
    try {
      await api.post("/auth/mfa/disable", { password: disablePassword, code: disableCode });
      setDisablePassword("");
      setDisableCode("");
      setRecoveryCodes([]);
      await refreshUser();
      toast.success("Double authentification désactivée.");
    } catch (err) {
      toast.error(formatApiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="border-slate-200 shadow-sm p-6 lg:col-span-2" data-testid="settings-mfa">
      <div className="flex items-center gap-2 mb-4">
        <ShieldCheck size={16} className="text-slate-500" />
        <p className="font-display text-lg font-semibold">Double authentification</p>
        <span className={`ml-auto text-xs font-medium ${enabled ? "text-emerald-600" : "text-slate-500"}`}>
          {enabled ? "Activée" : "Désactivée"}
        </span>
      </div>

      {recoveryCodes.length > 0 && (
        <div className="mb-5 rounded-lg border border-amber-300 bg-amber-50 p-4" data-testid="mfa-recovery-codes">
          <p className="text-sm font-semibold text-amber-900">Codes de secours — à conserver maintenant</p>
          <p className="text-xs text-amber-800 mt-1">
            Ils ne seront plus affichés. Chaque code sert une seule fois si vous perdez votre téléphone.
          </p>
          <div className="mt-3 grid grid-cols-2 gap-1 font-mono text-sm">
            {recoveryCodes.map((c) => <span key={c}>{c}</span>)}
          </div>
          <Button variant="outline" size="sm" className="mt-3" onClick={() => copyText(recoveryCodes.join("\n"))}>
            <Copy size={13} className="mr-1.5" /> Copier les codes
          </Button>
        </div>
      )}

      {!enabled && !setup && (
        <>
          <p className="text-sm text-slate-600 mb-4">
            Protégez le compte administrateur avec une application d'authentification (Google Authenticator,
            Microsoft Authenticator, 1Password…). Le mot de passe seul ne suffira plus.
          </p>
          <div className="max-w-sm space-y-1.5">
            <Label htmlFor="mfa-password">Mot de passe actuel</Label>
            <Input
              id="mfa-password" type="password" value={password} autoComplete="current-password"
              onChange={(e) => setPassword(e.target.value)} data-testid="mfa-password-input"
            />
          </div>
          <Button className="mt-4" onClick={startSetup} disabled={busy || password.length < 1} data-testid="mfa-start-btn">
            <KeyRound size={14} className="mr-2" /> Configurer la double authentification
          </Button>
        </>
      )}

      {setup && (
        <div className="space-y-4" data-testid="mfa-setup-panel">
          <p className="text-sm text-slate-600">
            Scannez ce QR code avec votre application d'authentification, ou saisissez le secret
            ci-dessous, puis validez avec le code à 6 chiffres.
          </p>
          {setup.qr_code && (
            <div className="flex justify-center rounded-lg border border-slate-200 bg-white p-3">
              <img src={setup.qr_code} alt="QR code de configuration MFA" className="h-48 w-48" data-testid="mfa-qr-code" />
            </div>
          )}
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs uppercase tracking-wide text-slate-500">Secret</p>
            <p className="mt-1 font-mono text-lg break-all" data-testid="mfa-secret">{formatSecret(setup.secret)}</p>
            <Button variant="outline" size="sm" className="mt-2" onClick={() => copyText(setup.secret)}>
              <Copy size={13} className="mr-1.5" /> Copier le secret
            </Button>
          </div>
          <div className="max-w-sm space-y-1.5">
            <Label htmlFor="mfa-confirm-code">Code à 6 chiffres</Label>
            <Input
              id="mfa-confirm-code" inputMode="numeric" autoComplete="one-time-code" value={code}
              onChange={(e) => setCode(e.target.value)} data-testid="mfa-confirm-code-input"
              placeholder="123456"
            />
          </div>
          <div className="flex gap-2">
            <Button onClick={confirmSetup} disabled={busy || code.trim().length < 6} data-testid="mfa-confirm-btn">
              Activer
            </Button>
            <Button variant="outline" onClick={() => { setSetup(null); setCode(""); }} disabled={busy}>
              Annuler
            </Button>
          </div>
        </div>
      )}

      {enabled && (
        <div className="space-y-4" data-testid="mfa-enabled-panel">
          <p className="text-sm text-slate-600">
            La double authentification est active. Pour la désactiver, confirmez avec votre mot de passe
            et un code TOTP ou un code de secours.
          </p>
          <div className="grid gap-3 sm:grid-cols-2 max-w-xl">
            <div className="space-y-1.5">
              <Label htmlFor="mfa-disable-password">Mot de passe</Label>
              <Input id="mfa-disable-password" type="password" value={disablePassword}
                onChange={(e) => setDisablePassword(e.target.value)} data-testid="mfa-disable-password" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="mfa-disable-code">Code TOTP ou code de secours</Label>
              <Input id="mfa-disable-code" value={disableCode}
                onChange={(e) => setDisableCode(e.target.value)} data-testid="mfa-disable-code" />
            </div>
          </div>
          <Button variant="destructive" onClick={disable} disabled={busy || disablePassword.length < 1 || disableCode.trim().length < 6} data-testid="mfa-disable-btn">
            Désactiver la double authentification
          </Button>
        </div>
      )}
    </Card>
  );
}
