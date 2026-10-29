import React, { useMemo, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Upload, FileSpreadsheet, ArrowRight, ArrowLeft, CheckCircle2, AlertCircle, Info } from "lucide-react";

// iter138 : Import fichier clients (CSV/XLSX) — wizard 4 étapes.
// STRICT : ne crée QUE des fiches clients. Aucune vente / chantier / intervention / facture.
const STEP_UPLOAD = 1;
const STEP_MAPPING = 2;
const STEP_PREVIEW = 3;
const STEP_DONE = 4;

const DUP_OPTIONS = [
  { value: "ignore", label: "Ignorer les doublons", desc: "Les clients déjà existants (même téléphone ou email) sont sautés." },
  { value: "update", label: "Mettre à jour les doublons", desc: "Les champs non vides du fichier écrasent les valeurs existantes." },
  { value: "create", label: "Créer quand même", desc: "Une nouvelle fiche est créée même si un doublon existe (attention aux doublons volontaires)." },
];

export default function ImportClientsFileDialog({ open, onOpenChange, onImported }) {
  const [step, setStep] = useState(STEP_UPLOAD);
  const [file, setFile] = useState(null);
  const [parsing, setParsing] = useState(false);
  const [importing, setImporting] = useState(false);

  const [fields, setFields] = useState([]);
  const [importId, setImportId] = useState(null);
  const [headers, setHeaders] = useState([]);
  const [preview, setPreview] = useState([]);
  const [allRows, setAllRows] = useState([]);
  const [rowCount, setRowCount] = useState(0);
  const [mapping, setMapping] = useState({}); // { "0": "name", "1": "phone", ... }
  const [strategy, setStrategy] = useState("ignore");
  // iter146 : pré-rangement optionnel dans une catégorie (ex. "archives")
  const [archiveOnImport, setArchiveOnImport] = useState(false);
  const [result, setResult] = useState(null);

  const reset = () => {
    setStep(STEP_UPLOAD);
    setFile(null);
    setFields([]);
    setImportId(null);
    setHeaders([]);
    setPreview([]);
    setAllRows([]);
    setRowCount(0);
    setMapping({});
    setStrategy("ignore");
    setArchiveOnImport(false);
    setResult(null);
    setParsing(false);
    setImporting(false);
  };

  const close = () => { reset(); onOpenChange(false); };

  const onFileSelected = (f) => {
    if (!f) return;
    const okExt = /\.(csv|tsv|txt|xlsx|xlsm)$/i.test(f.name);
    if (!okExt) { toast.error("Format non supporté (CSV, TSV, XLSX)"); return; }
    if (f.size > 10 * 1024 * 1024) { toast.error("Fichier trop volumineux (max 10 Mo)"); return; }
    setFile(f);
  };

  const parseFile = async () => {
    if (!file) return;
    setParsing(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/clients/import/parse", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setFields(data.fields || []);
      setImportId(data.import_id || null);
      setHeaders(data.headers || []);
      setPreview(data.preview || []);
      setAllRows(data.rows_full || []); // legacy server fallback only
      setRowCount(data.row_count || 0);
      setMapping(data.auto_mapping || {});
      setStep(STEP_MAPPING);
    } catch (err) {
      toast.error(formatApiError(err));
    } finally { setParsing(false); }
  };

  const usedFields = useMemo(() => {
    const s = new Set();
    for (const v of Object.values(mapping)) if (v) s.add(v);
    return s;
  }, [mapping]);

  // iter148 : le nom peut être mappé via `name` OU (`first_name` et/ou `last_name`)
  const nameMapped = Object.values(mapping).some((v) => v === "name" || v === "first_name" || v === "last_name");

  const setColumnField = (colIdx, fieldKey) => {
    setMapping((prev) => {
      const next = { ...prev };
      for (const k of Object.keys(next)) if (next[k] === fieldKey && k !== String(colIdx)) delete next[k];
      if (!fieldKey) delete next[String(colIdx)];
      else next[String(colIdx)] = fieldKey;
      return next;
    });
  };

  const doImport = async () => {
    setImporting(true);
    try {
      const { data } = await api.post("/clients/import/execute", {
        mapping,
        import_id: importId,
        rows: importId ? [] : allRows,
        duplicate_strategy: strategy,
        assign_category: archiveOnImport ? "archives" : null,
      });
      setResult(data);
      setStep(STEP_DONE);
      toast.success(`${data.created_count} créé(s)${data.updated_count ? `, ${data.updated_count} mis à jour` : ""}`);
      onImported?.();
    } catch (err) {
      toast.error(formatApiError(err));
    } finally { setImporting(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => (!v ? close() : onOpenChange(v))}>
      <DialogContent className="sm:max-w-4xl max-h-[92vh] overflow-y-auto" data-testid="import-clients-file-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-2xl">Importer un fichier clients</DialogTitle>
        </DialogHeader>

        {/* Stepper */}
        <div className="flex items-center gap-2 text-xs">
          {[
            { n: STEP_UPLOAD, label: "Fichier" },
            { n: STEP_MAPPING, label: "Correspondance" },
            { n: STEP_PREVIEW, label: "Aperçu & doublons" },
            { n: STEP_DONE, label: "Résultat" },
          ].map((s, idx) => (
            <React.Fragment key={s.n}>
              <div className={`flex items-center gap-1.5 ${step >= s.n ? "text-slate-900 font-semibold" : "text-slate-400"}`}>
                <span className={`h-5 w-5 rounded-full flex items-center justify-center text-[10px] ${step >= s.n ? "bg-slate-900 text-white" : "bg-slate-200 text-slate-500"}`}>{s.n}</span>
                {s.label}
              </div>
              {idx < 3 && <div className="flex-1 h-px bg-slate-200" />}
            </React.Fragment>
          ))}
        </div>

        {step === STEP_UPLOAD && (
          <div className="space-y-4">
            <div className="rounded-lg border border-blue-200 bg-blue-50/60 p-3 text-xs text-blue-900 flex gap-2">
              <Info size={14} className="mt-0.5 shrink-0" />
              <div>
                <p className="font-medium mb-1">Cet import crée uniquement des fiches Clients.</p>
                <p>Aucune vente, chantier, intervention ou facture ne sera générée. Vous mapperez chaque colonne à un champ QYLOT à l'étape suivante.</p>
              </div>
            </div>
            <label htmlFor="import-file-input" className="block cursor-pointer border-2 border-dashed border-slate-300 rounded-xl px-6 py-10 text-center hover:border-slate-900 hover:bg-slate-50 transition" data-testid="import-file-dropzone">
              <FileSpreadsheet size={28} className="mx-auto text-slate-400 mb-2" />
              <p className="text-sm font-medium text-slate-900">{file ? file.name : "Choisir un fichier CSV ou Excel"}</p>
              <p className="text-xs text-slate-500 mt-1">CSV, TSV, XLSX — jusqu'à 10 Mo</p>
              <input
                id="import-file-input"
                type="file"
                accept=".csv,.tsv,.txt,.xlsx,.xlsm"
                className="hidden"
                onChange={(e) => onFileSelected(e.target.files?.[0])}
                data-testid="import-file-input"
              />
            </label>
          </div>
        )}

        {step === STEP_MAPPING && (
          <div className="space-y-3">
            <p className="text-xs text-slate-600">
              Associez chaque colonne de votre fichier à un champ QYLOT. Les colonnes laissées sur « Ignorer » ne seront pas importées.
              Mappez soit <span className="font-semibold">Nom complet</span>, soit <span className="font-semibold">Prénom + Nom</span> (les deux colonnes seront concaténées automatiquement).
            </p>
            <div className="border border-slate-200 rounded-lg overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-slate-50 text-slate-500">
                  <tr className="text-left">
                    <th className="px-3 py-2">Colonne du fichier</th>
                    <th className="px-3 py-2">Exemple</th>
                    <th className="px-3 py-2 w-64">Champ QYLOT</th>
                  </tr>
                </thead>
                <tbody>
                  {headers.map((h, i) => {
                    const sample = preview[0]?.[i] || preview[1]?.[i] || "";
                    const current = mapping[String(i)] || "";
                    // iter145 : indique dans les options la colonne source (si déjà utilisée
                    // ailleurs) mais N'EMPÊCHE PAS la sélection — un clic réaffecte le champ
                    // à cette colonne et libère l'ancienne (setColumnField).
                    const fieldToOtherColumn = {};
                    for (const [colIdx, fkey] of Object.entries(mapping)) {
                      if (colIdx !== String(i) && fkey) fieldToOtherColumn[fkey] = colIdx;
                    }
                    return (
                      <tr key={i} className="border-t border-slate-100" data-testid={`import-map-row-${i}`}>
                        <td className="px-3 py-2 font-medium">{h || <span className="italic text-slate-400">Colonne {i + 1}</span>}</td>
                        <td className="px-3 py-2 text-slate-500 truncate max-w-[240px]">{sample}</td>
                        <td className="px-3 py-2">
                          <select
                            value={current}
                            onChange={(e) => setColumnField(i, e.target.value)}
                            className="h-8 w-full border border-slate-300 rounded-md px-2 text-xs bg-white"
                            data-testid={`import-map-select-${i}`}
                          >
                            <option value="">— Ignorer —</option>
                            {fields.map((f) => {
                              const otherCol = fieldToOtherColumn[f.key];
                              const otherHeader = otherCol != null ? (headers[Number(otherCol)] || `Colonne ${Number(otherCol) + 1}`) : null;
                              return (
                                <option key={f.key} value={f.key}>
                                  {f.label}{f.required ? " *" : ""}{otherHeader ? ` — actuellement sur « ${otherHeader} »` : ""}
                                </option>
                              );
                            })}
                          </select>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {!nameMapped && (
              <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-2.5 text-xs text-amber-900 flex items-center gap-2">
                <AlertCircle size={13} /> Vous devez mapper au moins une colonne à « Prénom », « Nom » ou « Nom complet » pour continuer.
              </div>
            )}
          </div>
        )}

        {step === STEP_PREVIEW && (
          <div className="space-y-3">
            <div className="border border-slate-200 rounded-lg overflow-hidden">
              <div className="px-3 py-2 bg-slate-50 border-b border-slate-200 text-xs font-medium text-slate-700">
                Aperçu — {rowCount} ligne(s) au total, 10 premières affichées
              </div>
              <div className="max-h-64 overflow-auto">
                <table className="w-full text-xs">
                  <thead className="bg-slate-50/60 sticky top-0">
                    <tr className="text-left text-slate-500">
                      {fields.map((f) => {
                        const mapped = Object.entries(mapping).find(([, v]) => v === f.key);
                        return <th key={f.key} className="px-2.5 py-1.5">{f.label}{!mapped && <span className="text-slate-300"> —</span>}</th>;
                      })}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.slice(0, 10).map((row, i) => (
                      <tr key={i} className="border-t border-slate-100" data-testid={`import-preview-row-${i}`}>
                        {fields.map((f) => {
                          const entry = Object.entries(mapping).find(([, v]) => v === f.key);
                          const colIdx = entry ? Number(entry[0]) : null;
                          const v = colIdx != null ? row[colIdx] : "";
                          return <td key={f.key} className="px-2.5 py-1.5 truncate max-w-[220px]">{v || <span className="text-slate-300">—</span>}</td>;
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold text-slate-700">Que faire en cas de doublon (téléphone ou email déjà présents) ?</Label>
              <div className="grid gap-2">
                {DUP_OPTIONS.map((opt) => (
                  <label key={opt.value} className={`cursor-pointer rounded-lg border p-2.5 text-xs flex gap-2 ${strategy === opt.value ? "border-slate-900 bg-slate-50" : "border-slate-200"}`} data-testid={`import-dup-${opt.value}`}>
                    <input
                      type="radio"
                      name="dup"
                      value={opt.value}
                      checked={strategy === opt.value}
                      onChange={() => setStrategy(opt.value)}
                      className="mt-0.5"
                    />
                    <div>
                      <p className="font-semibold text-slate-900">{opt.label}</p>
                      <p className="text-slate-500">{opt.desc}</p>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            {/* iter146 : ranger les nouveaux clients directement dans Archivés */}
            <label className="flex items-start gap-2 rounded-lg border border-slate-200 p-2.5 text-xs cursor-pointer hover:bg-slate-50" data-testid="import-archive-on-create">
              <input
                type="checkbox"
                checked={archiveOnImport}
                onChange={(e) => setArchiveOnImport(e.target.checked)}
                className="mt-0.5"
              />
              <div>
                <p className="font-semibold text-slate-900">Ranger les nouveaux clients dans « Archivés »</p>
                <p className="text-slate-500">Utile pour importer un historique en masse sans encombrer la vue principale. S'applique uniquement aux fiches créées (pas aux doublons ignorés ni mis à jour).</p>
              </div>
            </label>
          </div>
        )}

        {step === STEP_DONE && result && (
          <div className="space-y-3">
            <div className="rounded-lg border border-emerald-200 bg-emerald-50/60 p-3 text-sm flex items-start gap-2">
              <CheckCircle2 size={16} className="text-emerald-700 mt-0.5" />
              <div>
                <p className="font-medium text-emerald-900">Import terminé</p>
                <ul className="text-emerald-800 text-xs mt-1 space-y-0.5">
                  <li>• {result.created_count} nouveau(x) client(s) créé(s)</li>
                  {result.updated_count > 0 && <li>• {result.updated_count} client(s) mis à jour</li>}
                  {result.skipped_count > 0 && <li>• {result.skipped_count} ligne(s) ignorée(s)</li>}
                  {result.error_count > 0 && <li>• {result.error_count} erreur(s)</li>}
                </ul>
              </div>
            </div>
            {result.skipped_count > 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50/40 p-2.5 text-xs" data-testid="import-skipped-list">
                <p className="font-semibold text-amber-900 mb-1">Détail des lignes ignorées :</p>
                <ul className="text-amber-800 space-y-0.5 max-h-32 overflow-y-auto">
                  {result.skipped.slice(0, 50).map((s, i) => (
                    <li key={i}>• Ligne {s.line} — {s.name || "?"} <span className="text-amber-700/70">({s.reason})</span></li>
                  ))}
                  {result.skipped.length > 50 && <li className="text-amber-600">…et {result.skipped.length - 50} autres</li>}
                </ul>
              </div>
            )}
          </div>
        )}

        <DialogFooter className="gap-2 flex-wrap">
          {step > STEP_UPLOAD && step < STEP_DONE && (
            <Button variant="outline" onClick={() => setStep((s) => Math.max(STEP_UPLOAD, s - 1))} data-testid="import-back-btn">
              <ArrowLeft size={13} className="mr-1" /> Précédent
            </Button>
          )}
          <Button variant="outline" onClick={close} data-testid="import-close-btn">Fermer</Button>
          {step === STEP_UPLOAD && (
            <Button onClick={parseFile} disabled={!file || parsing} data-testid="import-parse-btn">
              {parsing ? "Analyse…" : (<>Analyser <ArrowRight size={13} className="ml-1" /></>)}
            </Button>
          )}
          {step === STEP_MAPPING && (
            <Button onClick={() => setStep(STEP_PREVIEW)} disabled={!nameMapped} data-testid="import-next-preview-btn">
              Aperçu <ArrowRight size={13} className="ml-1" />
            </Button>
          )}
          {step === STEP_PREVIEW && (
            <Button onClick={doImport} disabled={importing || !nameMapped} data-testid="import-execute-btn">
              <Upload size={13} className="mr-1" />
              {importing ? "Import en cours…" : `Importer ${rowCount} ligne(s)`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
