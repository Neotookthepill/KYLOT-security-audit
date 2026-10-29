import React, { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { FileText, Sparkles, CheckCircle2, AlertCircle, Info, ArrowRight } from "lucide-react";

// iter143 : Import d'un devis PDF → extrait uniquement les infos client via IA.
// STRICT : ne crée QU'UNE fiche client. Aucune vente / chantier / facture générée.
const STEP_UPLOAD = 1;
const STEP_REVIEW = 2;
const STEP_DONE = 3;

const DUP_OPTIONS = [
  { value: "ignore", label: "Ne pas créer (garder la fiche existante)" },
  { value: "update", label: "Mettre à jour la fiche existante" },
  { value: "create", label: "Créer quand même (doublon volontaire)" },
];

const CONF_STYLE = {
  high: { label: "Extraction fiable", cls: "bg-emerald-50 text-emerald-800 border-emerald-200" },
  medium: { label: "À vérifier", cls: "bg-amber-50 text-amber-800 border-amber-200" },
  low: { label: "Extraction incertaine — corrigez si besoin", cls: "bg-red-50 text-red-800 border-red-200" },
};

export default function ImportClientPdfDialog({ open, onOpenChange, onImported }) {
  const [step, setStep] = useState(STEP_UPLOAD);
  const [file, setFile] = useState(null);
  const [parsing, setParsing] = useState(false);
  const [saving, setSaving] = useState(false);

  const [form, setForm] = useState({ name: "", phone: "", email: "", address: "", postal_code: "", city: "", devis_date: "" });
  const [confidence, setConfidence] = useState("medium");
  const [duplicate, setDuplicate] = useState(null);
  const [pages, setPages] = useState(0);
  const [strategy, setStrategy] = useState("ignore");
  const [archiveOnImport, setArchiveOnImport] = useState(false);
  const [result, setResult] = useState(null);

  const reset = () => {
    setStep(STEP_UPLOAD); setFile(null); setParsing(false); setSaving(false);
    setForm({ name: "", phone: "", email: "", address: "", postal_code: "", city: "", devis_date: "" });
    setConfidence("medium"); setDuplicate(null); setPages(0); setStrategy("ignore"); setArchiveOnImport(false); setResult(null);
  };
  const close = () => { reset(); onOpenChange(false); };

  const onFileSelected = (f) => {
    if (!f) return;
    if (!/\.(pdf|png|jpg|jpeg|webp|heic)$/i.test(f.name)) { toast.error("Format non supporté (PDF ou image)"); return; }
    if (f.size > 10 * 1024 * 1024) { toast.error("Fichier trop volumineux (max 10 Mo)"); return; }
    setFile(f);
  };

  const analyze = async () => {
    if (!file) return;
    setParsing(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/clients/import/pdf/parse", fd, { headers: { "Content-Type": "multipart/form-data" }, timeout: 60000 });
      const c = data.client || {};
      setForm({
        name: c.name || "",
        phone: c.phone || "",
        email: c.email || "",
        address: c.address || "",
        postal_code: c.postal_code || "",
        city: c.city || "",
        devis_date: c.devis_date || "",
      });
      setConfidence(c.confidence || "medium");
      setDuplicate(data.duplicate || null);
      setPages(data.pages_analyzed || 0);
      setStep(STEP_REVIEW);
    } catch (err) {
      toast.error(formatApiError(err));
    } finally { setParsing(false); }
  };

  const create = async () => {
    if (!form.name.trim()) { toast.error("Le nom du client est requis"); return; }
    setSaving(true);
    try {
      const { data } = await api.post("/clients/import/pdf/create", { ...form, duplicate_strategy: strategy, assign_category: archiveOnImport ? "archives" : null });
      setResult(data);
      setStep(STEP_DONE);
      if (data.action === "created") toast.success("Client créé");
      else if (data.action === "updated") toast.success("Fiche mise à jour");
      else toast.info("Fiche existante conservée");
      onImported?.();
    } catch (err) {
      toast.error(formatApiError(err));
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => (!v ? close() : onOpenChange(v))}>
      <DialogContent className="sm:max-w-3xl max-h-[92vh] overflow-y-auto" data-testid="import-client-pdf-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl flex items-center gap-2">
            <Sparkles size={20} className="text-violet-600" /> Importer un client depuis un devis PDF
          </DialogTitle>
        </DialogHeader>

        {step === STEP_UPLOAD && (
          <div className="space-y-4">
            <div className="rounded-lg border border-blue-200 bg-blue-50/60 p-3 text-xs text-blue-900 flex gap-2">
              <Info size={14} className="mt-0.5 shrink-0" />
              <div>
                <p className="font-medium mb-1">L'IA lit votre devis et pré-remplit la fiche client.</p>
                <p>Seules les infos client (nom, téléphone, email, adresse, CP, ville) et la date du devis sont extraites. Les produits, prestations et montants sont ignorés. Vous vérifiez ensuite avant création.</p>
              </div>
            </div>
            <label htmlFor="import-pdf-file" className="block cursor-pointer border-2 border-dashed border-slate-300 rounded-xl px-6 py-10 text-center hover:border-slate-900 hover:bg-slate-50 transition" data-testid="import-pdf-dropzone">
              <FileText size={28} className="mx-auto text-slate-400 mb-2" />
              <p className="text-sm font-medium text-slate-900">{file ? file.name : "Choisir un devis (PDF ou image)"}</p>
              <p className="text-xs text-slate-500 mt-1">PDF, PNG, JPG, WEBP, HEIC — jusqu'à 10 Mo</p>
              <input
                id="import-pdf-file"
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,.webp,.heic,application/pdf,image/*"
                className="hidden"
                onChange={(e) => onFileSelected(e.target.files?.[0])}
                data-testid="import-pdf-input"
              />
            </label>
          </div>
        )}

        {step === STEP_REVIEW && (
          <div className="space-y-4">
            <div className={`rounded-lg border p-2.5 text-xs flex items-center gap-2 ${(CONF_STYLE[confidence] || CONF_STYLE.medium).cls}`} data-testid="import-pdf-confidence">
              <Sparkles size={13} />
              <span>IA · {pages} page(s) analysée(s) — {(CONF_STYLE[confidence] || CONF_STYLE.medium).label}</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="sm:col-span-2">
                <Label>Nom / Prénom *</Label>
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="import-pdf-name" />
              </div>
              <div>
                <Label>Téléphone</Label>
                <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} data-testid="import-pdf-phone" />
              </div>
              <div>
                <Label>Email</Label>
                <Input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="import-pdf-email" />
              </div>
              <div className="sm:col-span-2">
                <Label>Adresse</Label>
                <Input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} data-testid="import-pdf-address" />
              </div>
              <div>
                <Label>Code postal</Label>
                <Input value={form.postal_code} onChange={(e) => setForm({ ...form, postal_code: e.target.value })} data-testid="import-pdf-cp" />
              </div>
              <div>
                <Label>Ville</Label>
                <Input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} data-testid="import-pdf-city" />
              </div>
              <div className="sm:col-span-2">
                <Label>Date du devis</Label>
                <Input type="date" value={form.devis_date} onChange={(e) => setForm({ ...form, devis_date: e.target.value })} data-testid="import-pdf-devis-date" />
                <p className="text-[11px] text-slate-500 mt-1">Ajoutée aux notes de la fiche client (« Devis du … »).</p>
              </div>
            </div>

            {duplicate && (
              <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3 text-xs" data-testid="import-pdf-duplicate">
                <div className="flex items-start gap-2">
                  <AlertCircle size={14} className="text-amber-700 mt-0.5 shrink-0" />
                  <div className="space-y-2 flex-1">
                    <p className="font-semibold text-amber-900">Un client existe déjà avec ce téléphone ou email :</p>
                    <p className="text-amber-900">{duplicate.name} {duplicate.city ? `· ${duplicate.city}` : ""} {duplicate.phone ? `· ${duplicate.phone}` : ""} {duplicate.email ? `· ${duplicate.email}` : ""}</p>
                    <div className="space-y-1 mt-1">
                      {DUP_OPTIONS.map((opt) => (
                        <label key={opt.value} className="flex items-center gap-2 cursor-pointer" data-testid={`import-pdf-dup-${opt.value}`}>
                          <input type="radio" name="pdf-dup" value={opt.value} checked={strategy === opt.value} onChange={() => setStrategy(opt.value)} />
                          <span>{opt.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* iter146 : ranger directement dans Archivés (proposition, désactivé par défaut) */}
            <label className="flex items-start gap-2 rounded-lg border border-slate-200 p-2.5 text-xs cursor-pointer hover:bg-slate-50" data-testid="import-pdf-archive">
              <input
                type="checkbox"
                checked={archiveOnImport}
                onChange={(e) => setArchiveOnImport(e.target.checked)}
                className="mt-0.5"
              />
              <div>
                <p className="font-semibold text-slate-900">Ranger dans « Archivés »</p>
                <p className="text-slate-500">La fiche sera pré-rangée dans la catégorie Archivés. Utile pour un devis d'historique sans suivi actif.</p>
              </div>
            </label>
          </div>
        )}

        {step === STEP_DONE && result && (
          <div className="space-y-3">
            <div className="rounded-lg border border-emerald-200 bg-emerald-50/60 p-3 text-sm flex items-start gap-2">
              <CheckCircle2 size={16} className="text-emerald-700 mt-0.5" />
              <div>
                {result.action === "created" && <p className="font-medium text-emerald-900">Client créé : {result.client?.name}</p>}
                {result.action === "updated" && <p className="font-medium text-emerald-900">Fiche mise à jour : {result.client?.name}</p>}
                {result.action === "skipped" && <p className="font-medium text-emerald-900">Fiche existante conservée : {result.existing?.name}</p>}
              </div>
            </div>
          </div>
        )}

        <DialogFooter className="gap-2 flex-wrap">
          <Button variant="outline" onClick={close} data-testid="import-pdf-close">Fermer</Button>
          {step === STEP_UPLOAD && (
            <Button onClick={analyze} disabled={!file || parsing} data-testid="import-pdf-analyze">
              {parsing ? "Analyse IA…" : (<>Analyser <ArrowRight size={13} className="ml-1" /></>)}
            </Button>
          )}
          {step === STEP_REVIEW && (
            <Button onClick={create} disabled={saving || !form.name.trim()} data-testid="import-pdf-create">
              {saving ? "Enregistrement…" : "Créer le client"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
