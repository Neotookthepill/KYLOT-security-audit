import { useEffect, useState } from "react";
import { WifiOff, RefreshCw, CheckCircle2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { subscribeOffline, resolveConflict } from "@/lib/offline";
import { syncOffline } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

const show = (v) => {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "object") return JSON.stringify(v).slice(0, 120);
  return String(v);
};

function ConflictDialog({ conflict }) {
  return (
    <Dialog open={!!conflict} onOpenChange={() => {}}>
      <DialogContent className="sm:max-w-lg [&>button]:hidden" onEscapeKeyDown={(e) => e.preventDefault()} onPointerDownOutside={(e) => e.preventDefault()} data-testid="offline-conflict-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><AlertTriangle size={18} className="text-amber-500" /> Modification en conflit</DialogTitle>
          <p className="text-sm text-slate-500">« {conflict?.label} » a été modifié par quelqu'un d'autre pendant que vous étiez hors ligne. Quelle version garder ?</p>
        </DialogHeader>
        <div className="border rounded-md overflow-hidden text-sm">
          <div className="grid grid-cols-3 bg-slate-50 px-3 py-2 overline"><span>Champ</span><span>Ma version</span><span>Version actuelle</span></div>
          {(conflict?.fields || []).map((f) => (
            <div key={f.key} className="grid grid-cols-3 px-3 py-2 border-t border-slate-100 gap-2">
              <span className="text-slate-500 break-words">{f.key.replace(/_/g, " ")}</span>
              <span className="font-medium text-indigo-700 break-words">{show(f.mine)}</span>
              <span className="font-medium text-slate-800 break-words">{show(f.server)}</span>
            </div>
          ))}
        </div>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => resolveConflict("server")} data-testid="offline-conflict-keep-server">Garder la version actuelle</Button>
          <Button onClick={() => resolveConflict("mine")} data-testid="offline-conflict-keep-mine">Garder ma version</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export const OfflineBar = () => {
  const [s, setS] = useState({ online: true, pending: 0, syncing: false, conflict: null });
  useEffect(() => subscribeOffline(setS), []);
  useEffect(() => {
    const onSynced = (e) => toast.success(`${e.detail.count} modification${e.detail.count > 1 ? "s" : ""} hors ligne synchronisée${e.detail.count > 1 ? "s" : ""}`, {
      action: { label: "Actualiser", onClick: () => window.location.reload() },
    });
    window.addEventListener("qylot:synced", onSynced);
    return () => window.removeEventListener("qylot:synced", onSynced);
  }, []);
  useEffect(() => { if (s.lastError) toast.error(`Synchronisation refusée — ${s.lastError}`); }, [s.lastError]);

  const visible = !s.online || s.pending > 0 || s.syncing;
  return (
    <>
      {visible && (
        <div className={`sticky top-0 z-40 flex items-center gap-2 px-4 py-2 text-sm ${s.online ? "bg-indigo-50 text-indigo-900 border-b border-indigo-100" : "bg-amber-100 text-amber-900 border-b border-amber-200"}`} data-testid="offline-bar">
          {s.online ? (s.syncing ? <RefreshCw size={15} className="animate-spin" /> : <CheckCircle2 size={15} />) : <WifiOff size={15} />}
          <span data-testid="offline-bar-text">
            {!s.online ? "Hors ligne — vous pouvez continuer à travailler." : s.syncing ? "Synchronisation en cours…" : "Connexion rétablie."}
            {s.pending > 0 && <b className="ml-1">{s.pending} modification{s.pending > 1 ? "s" : ""} en attente</b>}
          </span>
          {s.online && s.pending > 0 && !s.syncing && (
            <button type="button" onClick={() => syncOffline()} className="ml-auto text-xs font-semibold underline" data-testid="offline-sync-btn">Synchroniser</button>
          )}
        </div>
      )}
      <ConflictDialog conflict={s.conflict} />
    </>
  );
};
