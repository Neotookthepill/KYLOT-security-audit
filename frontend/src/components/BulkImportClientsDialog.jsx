import React, { useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { Upload, Info, CheckCircle2, AlertCircle } from "lucide-react";

const EXAMPLE = `Martin Dupont\t06 12 34 56 78\tm.dupont@mail.fr\t12 rue de la Paix\t69003\tLyon\tRecommandation
Sophie Bernard;06 98 76 54 32;s.bernard@mail.fr;45 av. des Fleurs;69100;Villeurbanne;`;

// Reproduce backend parser client-side for a live preview
function parseText(raw) {
  if (!raw) return [];
  const HEADERS = new Set(["nom", "prenom", "prénom", "name", "nom / prenom", "nom / prénom", "client"]);
  const rows = [];
  for (const line of raw.replace(/\r/g, "").split("\n")) {
    const l = line.trim();
    if (!l) continue;
    let parts;
    if (l.includes("\t")) parts = l.split("\t");
    else if (l.includes(";")) parts = l.split(";");
    else if ((l.match(/,/g) || []).length >= 2) parts = l.split(",");
    else parts = [l];
    parts = parts.map((p) => p.trim());
    if (parts[0] && HEADERS.has(parts[0].toLowerCase())) continue;
    while (parts.length < 7) parts.push("");
    const [name, phone, email, address, postal_code, city, notes] = parts;
    if (!name) continue;
    rows.push({ name, phone, email, address, postal_code, city, notes });
  }
  return rows;
}

export default function BulkImportClientsDialog({ open, onOpenChange, onImported }) {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const preview = useMemo(() => parseText(text), [text]);

  const submit = async () => {
    if (preview.length === 0) return toast.error("Aucune ligne détectée");
    setLoading(true);
    try {
      const res = await api.post("/clients/bulk", { text });
      setResult(res.data);
      toast.success(`${res.data.created_count} client(s) importé(s)`);
      onImported?.();
    } catch (err) {
      toast.error(formatApiError(err));
    } finally { setLoading(false); }
  };

  const close = () => {
    setText("");
    setResult(null);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={(v) => (!v ? close() : onOpenChange(v))}>
      <DialogContent className="sm:max-w-3xl max-h-[92vh] overflow-y-auto" data-testid="bulk-import-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl">Importer des clients (copier-coller)</DialogTitle>
        </DialogHeader>

        <div className="rounded-lg border border-blue-200 bg-blue-50/60 p-3 text-xs text-blue-900 flex gap-2">
          <Info size={14} className="mt-0.5 shrink-0" />
          <div className="space-y-1">
            <p className="font-medium">Format accepté (une ligne par client, colonnes séparées par tabulation, <span className="font-mono">;</span> ou <span className="font-mono">,</span>) :</p>
            <p className="font-mono text-[11px]">Nom Prénom · Téléphone · Email · Adresse · CP · Ville · Notes</p>
            <p>Astuce : depuis Excel ou Google Sheets, sélectionne les colonnes puis Ctrl+C → colle ici.</p>
          </div>
        </div>

        <Textarea
          rows={9}
          placeholder={EXAMPLE}
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="font-mono text-xs"
          data-testid="bulk-import-textarea"
        />

        {preview.length > 0 && !result && (
          <div className="border border-slate-200 rounded-lg overflow-hidden">
            <div className="px-3 py-2 bg-slate-50 border-b border-slate-200 text-xs font-medium text-slate-700">
              Aperçu — {preview.length} ligne(s) prête(s) à être importée(s)
            </div>
            <div className="max-h-56 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="bg-slate-50/50">
                  <tr className="text-left text-slate-500">
                    <th className="px-2.5 py-1.5">Nom</th>
                    <th className="px-2.5 py-1.5">Tél.</th>
                    <th className="px-2.5 py-1.5">Email</th>
                    <th className="px-2.5 py-1.5">Adresse</th>
                    <th className="px-2.5 py-1.5">CP</th>
                    <th className="px-2.5 py-1.5">Ville</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.slice(0, 50).map((c, i) => (
                    <tr key={i} className="border-t border-slate-100" data-testid={`bulk-preview-row-${i}`}>
                      <td className="px-2.5 py-1.5 font-medium">{c.name}</td>
                      <td className="px-2.5 py-1.5">{c.phone}</td>
                      <td className="px-2.5 py-1.5">{c.email}</td>
                      <td className="px-2.5 py-1.5">{c.address}</td>
                      <td className="px-2.5 py-1.5">{c.postal_code}</td>
                      <td className="px-2.5 py-1.5">{c.city}</td>
                    </tr>
                  ))}
                  {preview.length > 50 && (
                    <tr><td colSpan={6} className="px-2.5 py-1.5 text-center text-slate-500">…et {preview.length - 50} autres</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {result && (
          <div className="space-y-2">
            <div className="rounded-lg border border-emerald-200 bg-emerald-50/60 p-3 text-sm flex items-start gap-2">
              <CheckCircle2 size={16} className="text-emerald-700 mt-0.5" />
              <div>
                <p className="font-medium text-emerald-900">{result.created_count} client(s) créé(s)</p>
                {result.skipped_count > 0 && (
                  <p className="text-emerald-800/80 text-xs">{result.skipped_count} déjà présent(s), ignoré(s).</p>
                )}
              </div>
            </div>
            {result.skipped_count > 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50/40 p-3 text-xs flex items-start gap-2" data-testid="bulk-import-skipped">
                <AlertCircle size={14} className="text-amber-700 mt-0.5" />
                <div>
                  <p className="font-medium text-amber-900 mb-1">Doublons ignorés :</p>
                  <ul className="text-amber-800/80 space-y-0.5 max-h-24 overflow-y-auto">
                    {result.skipped.map((s, i) => (<li key={i}>• {s.name} <span className="text-amber-700/60">— {s.reason}</span></li>))}
                  </ul>
                </div>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={close}>Fermer</Button>
          {!result && (
            <Button onClick={submit} disabled={loading || preview.length === 0} data-testid="bulk-import-submit">
              <Upload size={14} className="mr-1.5" />
              {loading ? "Import en cours…" : `Importer ${preview.length} client(s)`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
