import React, { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ShieldAlert, CalendarClock } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import MfaSettingsCard from "@/components/MfaSettingsCard";

/**
 * Mandatory-MFA notice. During the grace period this is a non-blocking banner.
 * Once the deadline has passed, the setup dialog cannot be dismissed and the
 * backend also blocks all non-auth API calls.
 */
export default function MfaRequiredNotice() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const required = Boolean(user?.mfa_setup_required);
  const expired = Boolean(user?.mfa_grace_expired);

  useEffect(() => {
    if (!required) setOpen(false);
    else if (expired) setOpen(true);
  }, [required, expired]);

  if (!user || !required) return null;

  const until = user.mfa_grace_until ? new Date(user.mfa_grace_until) : null;
  const untilLabel = until && !Number.isNaN(until.getTime())
    ? until.toLocaleDateString("fr-FR", { day: "2-digit", month: "long", year: "numeric" })
    : "bientôt";

  return (
    <>
      <div
        data-testid="mfa-required-banner"
        className={`${expired ? "bg-red-50 border-red-300 text-red-900" : "bg-amber-50 border-amber-300 text-amber-900"} border-b px-4 py-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm`}
      >
        <ShieldAlert size={16} className="shrink-0" />
        <span className="font-semibold">Double authentification obligatoire.</span>
        <span className="flex items-center gap-1">
          <CalendarClock size={13} />
          {expired
            ? "Votre délai est dépassé : configurez-la maintenant."
            : `À activer avant le ${untilLabel}.`}
        </span>
        <Button
          size="sm"
          variant={expired ? "destructive" : "outline"}
          className="ml-auto h-7"
          onClick={() => setOpen(true)}
          data-testid="mfa-required-open"
        >
          Configurer
        </Button>
      </div>

      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (!next && expired) return;
          setOpen(next);
        }}
      >
        <DialogContent
          className="max-w-xl max-h-[90vh] overflow-y-auto"
          data-testid="mfa-required-dialog"
          onEscapeKeyDown={(e) => { if (expired) e.preventDefault(); }}
          onInteractOutside={(e) => { if (expired) e.preventDefault(); }}
        >
          <DialogHeader>
            <DialogTitle className="font-display text-xl">
              {expired ? "Accès bloqué : MFA obligatoire" : "Activez la double authentification"}
            </DialogTitle>
          </DialogHeader>
          <p className="text-sm text-slate-600">
            {expired
              ? "Le délai de grâce est terminé. Tant que la MFA n'est pas activée, les données de l'entreprise restent inaccessibles."
              : `Vous pouvez encore utiliser KYLOT, mais la MFA doit être activée avant le ${untilLabel}.`}
          </p>
          <MfaSettingsCard />
        </DialogContent>
      </Dialog>
    </>
  );
}
