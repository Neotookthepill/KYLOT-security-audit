import React, { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Bot, Send, X, Loader2, Sparkles, MessageSquare, Check, XCircle, AlertCircle, Paperclip, FileText, Image as ImageIcon, ArrowRight, Mic, MicOff } from "lucide-react";
import { toast } from "sonner";
import { formatRate, PAYMENT_LABELS } from "@/lib/saleConstants";

const CHAT_SUGGESTIONS = [
  "Comment créer une vente ?",
  "Analyse ce devis (joins une photo/PDF)",
  "Résume-moi les prestations vendues",
];
const ACTION_SUGGESTIONS = [
  "Vente Kilian 5000€ 20% chez Dupont R1",
  "Vente Theo 3200€ 13% financement chez Martin CQ",
  "Nouveau client Marie Bernard 06 12 34 56 78 à Lyon",
];

const fmtEur = (n) => new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(n || 0);
const STATUS_LABELS = { en_cours: "PROG", commercial_cheque: "Commercial a le chèque", argent_recupere: "Argent récupéré", chantier_fini: "Chantier fini", litige: "Litige", annule: "Annulé" };
const DRAFT_KEY_BASE = "kylot_ai_draft_v1";
const AI_TIMEOUT_MS = 60000;
const ASSISTANT_NAME = "KIK'S"; // iter69 : nom de l'assistant IA (l'app reste "Ki-lot")

// iter182 — Nouvel avatar KIK'S : identique au style Emergent — rond noir plein
// avec un petit glyphe blanc (bulle de dialogue) centré. Minimaliste, monochrome,
// s'aligne avec le nouveau branding QYLOT (noir/blanc).
function KiksAvatar({ size = 24, className = "", ringed = true }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      className={`inline-block ${ringed ? "ring-1 ring-white/20 shadow-sm rounded-full" : ""} ${className}`}
      aria-label="KIK'S"
      role="img"
    >
      {/* Cercle noir plein */}
      <circle cx="16" cy="16" r="15" fill="#0b0d13" />
      {/* Petite bulle de dialogue blanche + queue */}
      <path
        d="M10 12.5 a3.2 3.2 0 0 1 3.2 -3.2 h5.6 a3.2 3.2 0 0 1 3.2 3.2 v3.6 a3.2 3.2 0 0 1 -3.2 3.2 h-3.6 l-2.6 2.4 v-2.4 h0.6 a3.2 3.2 0 0 1 -3.2 -3.2 z"
        fill="#FFFFFF"
      />
    </svg>
  );
}

// Compress iPhone/Android photos before upload (long side max 1600px, jpeg 0.82)
const compressImage = (file) => new Promise((resolve) => {
  if (!file.type?.startsWith("image/")) return resolve(file);
  const img = new Image();
  const reader = new FileReader();
  reader.onload = (e) => { img.src = e.target.result; };
  img.onload = () => {
    try {
      const MAX = 1600;
      let { width, height } = img;
      if (Math.max(width, height) > MAX) {
        const r = MAX / Math.max(width, height);
        width = Math.round(width * r); height = Math.round(height * r);
      }
      const canvas = document.createElement("canvas");
      canvas.width = width; canvas.height = height;
      canvas.getContext("2d").drawImage(img, 0, 0, width, height);
      canvas.toBlob((blob) => {
        if (!blob) return resolve(file);
        resolve(new File([blob], file.name.replace(/\.(heic|heif)$/i, ".jpg"), { type: "image/jpeg" }));
      }, "image/jpeg", 0.82);
    } catch (_) { resolve(file); }
  };
  img.onerror = () => resolve(file);
  reader.onerror = () => resolve(file);
  reader.readAsDataURL(file);
});

// Timeout wrapper — never leaves the UI stuck forever
const withTimeout = (promise, ms = AI_TIMEOUT_MS) => Promise.race([
  promise,
  new Promise((_, rej) => setTimeout(() => rej(new Error("L'analyse prend trop de temps. Veuillez réessayer.")), ms)),
]);

// Field-filler: interpret a short reply as a value for the currently-missing field
const parseFieldAnswer = (missingField, text) => {
  const t = (text || "").trim();
  if (!t) return null;
  if (["commercial", "client_name", "client_address", "client_postal_code", "client_city", "bdc", "client_phone", "service", "source", "name", "email", "address"].includes(missingField)) return t;
  if (missingField === "amount") {
    const m = t.replace(/\s/g, "").replace(",", ".").match(/(\d+(?:\.\d+)?)/);
    return m ? parseFloat(m[1]) : null;
  }
  if (missingField === "commission_rate") {
    const m = t.replace("%", "").replace(",", ".").match(/(\d+(?:\.\d+)?)/);
    if (!m) return null;
    const n = parseFloat(m[1]);
    return n > 1 ? n / 100 : n;
  }
  if (missingField === "sale_date") {
    const m1 = t.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (m1) return t;
    const m2 = t.match(/^(\d{2})[\/.-](\d{2})[\/.-](\d{4})$/);
    if (m2) return `${m2[3]}-${m2[2]}-${m2[1]}`;
    return null;
  }
  if (missingField === "payment_method") {
    const l = t.toLowerCase();
    if (l.includes("finan")) return "financement";
    if (l.includes("cheque") || l.includes("chèque")) return "cheque";
    if (l.includes("comptant")) return "comptant";
    if (l.includes("prélèv") || l.includes("prelev")) return "prelevement";
    if (l === "rac") return "rac";
    return null;
  }
  return t; // generic
};

const FIELD_LABELS = {
  commercial: "Commercial",
  client_name: "Client",
  client_phone: "Téléphone",
  client_address: "Adresse",
  client_postal_code: "Code postal",
  client_city: "Ville",
  amount: "Montant",
  commission_rate: "Commission",
  sale_date: "Date",
  payment_method: "Règlement",
  bdc: "N° devis",
  service: "Prestations",
  source: "Source",
  status: "Statut",
};
const labelFor = (f) => FIELD_LABELS[f] || f;

const FIELD_QUESTIONS = {
  commercial: "Quel est le commercial ?",
  client_name: "Quel est le nom du client ?",
  client_phone: "Quel est le numéro de téléphone ?",
  client_address: "Quelle est l'adresse ?",
  client_postal_code: "Quel est le code postal ?",
  client_city: "Quelle est la ville ?",
  amount: "Quel est le montant HT ?",
  commission_rate: "Quel taux de commission ? (ex : 15%)",
  sale_date: "Quelle date ? (JJ/MM/AAAA)",
  payment_method: "Quel règlement ? (Chèque / Comptant / Financement / Prélèvement / RAC)",
  bdc: "Quel est le numéro de devis ?",
  service: "Quelles prestations ?",
  status: "Quel statut ? (En cours / Argent récupéré…)",
};
const questionFor = (f) => `${labelFor(f)} à compléter — ${FIELD_QUESTIONS[f] || `Réponds pour compléter : ${labelFor(f)}`}`;

function ActionPreviewCard({ preview, onConfirm, onCancel, executing, capabilities = {}, onFieldUpdate }) {
  const { intent, data, missing, summary, confidence } = preview;
  // Hooks MUST be declared unconditionally — hoisted above the early return below to satisfy
  // React's rules-of-hooks (CRA/craco fails the build on ESLint hook violations).
  const [editing, setEditing] = useState(null); // field key
  const [draft, setDraft] = useState("");
  const confidenceColor = confidence === "high" ? "text-emerald-700 bg-emerald-50 border-emerald-200"
    : confidence === "medium" ? "text-amber-800 bg-amber-50 border-amber-200"
    : "text-slate-600 bg-slate-100 border-slate-200";

  if (intent === "unknown") {
    return (
      <div className="bg-white border border-amber-200 rounded-xl p-3 shadow-sm">
        <div className="flex items-center gap-2 text-sm text-amber-800">
          <AlertCircle size={14} />
          <span>Je n'ai pas compris l'action. Essayez : « Vente Kilian 5000€ 20% chez Dupont R1 »</span>
        </div>
      </div>
    );
  }

  const missingBlocking = missing.filter((m) => m !== "commercial");
  // Role-based hard gate: a commercial cannot validate a sale creation / status update
  // through the AI assistant, regardless of what the preview looks like.
  const roleAllows =
    (intent === "create_sale" && capabilities.canCreateSale) ||
    (intent === "create_client" && capabilities.canCreateClient) ||
    (intent === "update_sale_status" && capabilities.canEditSale) ||
    !["create_sale", "create_client", "update_sale_status"].includes(intent);
  const canConfirm = missingBlocking.length === 0 && roleAllows;

  // Inline field editing inside the preview card. Any field (missing, uncertain, or wrong)
  // is directly clickable and rewritten in-place — no need to type into the chat below.
  const startEdit = (field, current) => { setEditing(field); setDraft(current == null ? "" : String(current)); };
  const commit = () => {
    if (!editing) return;
    let val = draft.trim();
    if (editing === "amount") { const n = parseFloat(val.replace(",", ".").replace(/[^\d.]/g, "")); val = isFinite(n) ? n : val; }
    onFieldUpdate?.(editing, val);
    setEditing(null); setDraft("");
  };
  const cancel = () => { setEditing(null); setDraft(""); };
  const editable = (field, currentValue, opts = {}) => {
    const { fmt, placeholder = "À compléter" } = opts;
    if (editing === field) {
      return (
        <input autoFocus value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commit(); } if (e.key === "Escape") cancel(); }}
          className="h-6 px-1.5 text-xs border border-slate-400 rounded focus:outline-none focus:ring-1 focus:ring-slate-900 w-full max-w-[240px]"
          data-testid={`ai-preview-input-${field}`}
        />
      );
    }
    const empty = currentValue == null || currentValue === "";
    return (
      <button type="button" onClick={() => startEdit(field, currentValue)}
        className={`text-left rounded px-1 hover:bg-slate-100 hover:ring-1 hover:ring-slate-300 transition inline-flex items-center gap-1 ${empty ? "text-red-600" : "text-slate-800"}`}
        title="Cliquer pour modifier"
        data-testid={`ai-preview-edit-${field}`}
      >
        {empty ? (
          <span className="italic">{placeholder} ✎</span>
        ) : (
          <span>{fmt ? fmt(currentValue) : currentValue} <span className="text-slate-400 text-[10px]">✎</span></span>
        )}
      </button>
    );
  };
  const title = intent === "create_sale" ? "Vente préparée"
    : intent === "create_client" ? "Créer un client"
    : intent === "update_sale_status" ? "Changer le statut d'une vente"
    : intent;
  const executingLabel = intent === "update_sale_status" ? "Mise à jour…" : "Ouverture…";
  const confirmLabel = intent === "update_sale_status" ? "Mettre à jour" : intent === "create_sale" ? "Voir et valider la vente" : "Confirmer";

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-sm space-y-2" data-testid="ai-action-preview">
      <div className="flex items-center gap-2">
        <Sparkles size={14} className="text-indigo-600" />
        <div className="text-sm font-semibold text-slate-900 flex-1">{title}</div>
        <span className={`text-[10px] px-1.5 py-0.5 rounded border uppercase tracking-wide ${confidenceColor}`}>{confidence}</span>
      </div>
      {summary && <div className="text-xs text-slate-600 italic">« {summary} »</div>}

      <div className="rounded-lg bg-slate-50/70 border border-slate-100 p-2.5 space-y-1 text-xs">
        {intent === "create_sale" && (
          <>
            <Row label="Client" value={editable("client_name", data.client_name)} />
            <Row label="N° devis" value={editable("bdc", data.bdc, { placeholder: "Optionnel" })} />
            <Row label="Date" value={editable("sale_date", data.sale_date, { placeholder: "JJ/MM/AAAA" })} />
            <Row label="Commercial" value={editable("commercial", data.commercial, { placeholder: "À compléter (optionnel)" })} />
            <Row label="Montant" value={editable("amount", data.amount, { fmt: (v) => fmtEur(v) })} />
            {data.service && (
              <Row label={`Prestation${data.prestations_count > 1 ? "s" : ""}${data.prestations_count ? ` (${data.prestations_count})` : ""}`} value={<span className="whitespace-pre-wrap block break-words">{data.service}</span>} />
            )}
            <Row label="Adresse" value={editable("client_address", data.client_address, { placeholder: "Optionnel" })} />
            <Row label="Téléphone" value={editable("client_phone", data.client_phone, { placeholder: "Optionnel" })} />
          </>
        )}
        {intent === "create_client" && (
          <>
            <Row label="Nom" value={editable("name", data.name)} />
            <Row label="Téléphone" value={editable("phone", data.phone, { placeholder: "Optionnel" })} />
            <Row label="Email" value={editable("email", data.email, { placeholder: "Optionnel" })} />
            <Row label="Adresse" value={editable("address", data.address, { placeholder: "Optionnel" })} />
          </>
        )}
        {intent === "update_sale_status" && (
          <>
            <Row label="Client" value={data.client_name || <em className="text-red-500">non trouvé</em>} />
            {data.bdc && <Row label="BDC" value={data.bdc} />}
            <Row label="Statut" value={
              <span className="inline-flex items-center gap-1.5">
                {data.current_status && (<><span className="text-slate-400 line-through">{STATUS_LABELS[data.current_status] || data.current_status}</span><span className="text-slate-400">→</span></>)}
                <span className="text-emerald-700 font-semibold">{STATUS_LABELS[data.status] || data.status || <em className="text-red-500">manquant</em>}</span>
              </span>
            } />
          </>
        )}
      </div>

      {missing.length > 0 && (() => {
        const blocking = missing.filter((m) => m !== "commercial");
        if (blocking.length === 0) {
          return (
            <div className="text-[11px] text-slate-600 bg-slate-50 border border-slate-200 rounded-md px-2 py-1.5 flex items-start gap-1">
              <AlertCircle size={12} className="mt-0.5 shrink-0 text-slate-500" />
              <span>Commercial non identifié — vous pouvez valider maintenant et le renseigner plus tard.</span>
            </div>
          );
        }
        return (
          <div className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-2 py-1.5 flex items-start gap-1">
            <AlertCircle size={12} className="mt-0.5 shrink-0" />
            <span>Information à compléter — cliquez sur les champs en rouge ci-dessus, ou répondez ci-dessous : <strong>{blocking.map(labelFor).join(", ")}</strong></span>
          </div>
        );
      })()}

      {!roleAllows && (
        <div className="text-[11px] text-slate-700 bg-slate-100 border border-slate-300 rounded-md px-2 py-1.5 flex items-start gap-1" data-testid="ai-role-blocked">
          <AlertCircle size={12} className="mt-0.5 shrink-0 text-slate-500" />
          <span>
            {intent === "create_sale" && "Seuls Admin / Responsable peuvent créer une vente. Transmettez cet aperçu à votre responsable pour validation."}
            {intent === "update_sale_status" && "Seuls Admin / Responsable peuvent modifier une vente."}
            {intent === "create_client" && "Vous n'avez pas la permission de créer un client."}
          </span>
        </div>
      )}

      <div className="flex gap-2 pt-1">
        <button onClick={onCancel} disabled={executing} className="flex-1 h-8 text-xs rounded-md border border-slate-200 text-slate-600 hover:bg-slate-50 flex items-center justify-center gap-1" data-testid="ai-action-cancel">
          <XCircle size={12} /> Annuler
        </button>
        <button onClick={onConfirm} disabled={!canConfirm || executing} className="flex-[2] h-8 text-xs rounded-md bg-slate-900 text-white hover:bg-slate-800 disabled:opacity-40 flex items-center justify-center gap-1" data-testid="ai-action-confirm">
          {executing ? <Loader2 size={12} className="animate-spin" /> : intent === "create_sale" ? <ArrowRight size={12} /> : <Check size={12} />}
          {executing ? executingLabel : confirmLabel}
        </button>
      </div>
    </div>
  );
}

const Row = ({ label, value }) => (
  <div className="flex gap-2">
    <span className="text-slate-500 uppercase tracking-wider text-[10px] w-20 shrink-0 pt-0.5">{label}</span>
    <span className="text-slate-800 font-medium flex-1 break-words">{value}</span>
  </div>
);

export default function AIHelper() {
  const nav = useNavigate();
  const { user, can } = useAuth();
  const DRAFT_KEY = user?.id ? `${DRAFT_KEY_BASE}:${user.id}` : DRAFT_KEY_BASE;
  const capabilities = {
    canCreateSale: can("sales", "create"),
    canEditSale: can("sales", "edit"),
    canCreateClient: can("clients", "create"),
  };
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState("action");
  // Draft persisted in sessionStorage — survives navigation, panel toggle
  const [state, setState] = useState(() => {
    try {
      const raw = sessionStorage.getItem(DRAFT_KEY);
      if (raw) return JSON.parse(raw);
    } catch (_) {}
    return { messages: [], preview: null };
  });
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState([]);
  const [loading, setLoading] = useState(false);
  // iter69 : dictée vocale — Web Speech API (SpeechRecognition), transcription en direct
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef(null);
  const speechBaseRef = useRef(""); // texte figé au démarrage (permet d'ajouter à un input existant)
  const speechSupported = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);

  const stopDictation = useCallback(() => {
    try { recognitionRef.current && recognitionRef.current.stop(); } catch (_) {}
    setListening(false);
  }, []);

  const startDictation = useCallback(async () => {
    if (!speechSupported) {
      toast.error("La dictée vocale n'est pas disponible sur ce navigateur.");
      return;
    }
    // Demande explicite d'autorisation micro (améliore l'UX sur iOS/Safari)
    try {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        stream.getTracks().forEach((t) => t.stop());
      }
    } catch (err) {
      toast.error("Accès au microphone refusé. Autorisez le micro dans les réglages du navigateur.");
      return;
    }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec = new SR();
    rec.lang = "fr-FR";
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    speechBaseRef.current = input ? (input.endsWith(" ") ? input : input + " ") : "";
    rec.onresult = (event) => {
      let finalText = "";
      let interimText = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const t = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalText += t;
        else interimText += t;
      }
      // Concatène base + résultats live (finals + interim)
      const composed = (speechBaseRef.current + finalText + interimText).replace(/\s+/g, " ").trimStart();
      setInput(composed);
      if (finalText) speechBaseRef.current += finalText;
    };
    rec.onerror = (e) => {
      setListening(false);
      const errType = (e && e.error) || "";
      if (errType === "not-allowed" || errType === "service-not-allowed") {
        toast.error("Microphone refusé. Autorise l'accès et réessaie.");
      } else if (errType === "no-speech") {
        toast.info("Aucune parole détectée — appuie à nouveau sur le micro.");
      } else if (errType && errType !== "aborted") {
        toast.error("Erreur dictée : " + errType);
      }
    };
    rec.onend = () => setListening(false);
    recognitionRef.current = rec;
    try {
      rec.start();
      setListening(true);
    } catch (err) {
      // Some browsers throw when already started — force stop then retry once
      try { rec.stop(); } catch (_) {}
      setListening(false);
    }
  }, [input, speechSupported]);

  const toggleDictation = useCallback(() => {
    if (listening) stopDictation();
    else startDictation();
  }, [listening, startDictation, stopDictation]);

  useEffect(() => {
    // Cleanup au démontage
    return () => { try { recognitionRef.current && recognitionRef.current.stop(); } catch (_) {} };
  }, []);
  const [executing, setExecuting] = useState(false);
  const listRef = useRef(null);
  const cameraRef = useRef(null);
  const filesRef = useRef(null);
  const draftKeyRef = useRef(DRAFT_KEY);
  const skipNextDraftSaveRef = useRef(false);

  // A component can survive an identity refresh. Reload the new user's own
  // draft and explicitly skip the render that still contains the old state.
  useEffect(() => {
    if (draftKeyRef.current === DRAFT_KEY) return;
    draftKeyRef.current = DRAFT_KEY;
    skipNextDraftSaveRef.current = true;
    try {
      const raw = sessionStorage.getItem(DRAFT_KEY);
      setState(raw ? JSON.parse(raw) : { messages: [], preview: null });
    } catch (_) {
      setState({ messages: [], preview: null });
    }
  }, [DRAFT_KEY]);

  // Persist state safely (never crashes)
  useEffect(() => {
    if (skipNextDraftSaveRef.current) {
      skipNextDraftSaveRef.current = false;
      return;
    }
    try {
      sessionStorage.setItem(DRAFT_KEY, JSON.stringify({
        // Drop `files` from messages — File objects can't be serialised
        messages: state.messages.map((m) => ({ ...m, files: undefined })),
        preview: state.preview,
      }));
    } catch (_) {}
  }, [state, DRAFT_KEY]);

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [state.messages, loading]);

  const pushMessage = (msg) => setState((s) => ({ ...s, messages: [...s.messages, msg] }));
  const setPreview = (preview) => setState((s) => ({ ...s, preview }));

  // Inline field edit from ActionPreviewCard — updates preview.data + drops the field from `missing`.
  // Also logs a "correction" to the company's AI memory (best-effort — never blocks the UI).
  const updatePreviewField = (field, value) => {
    setState((s) => {
      if (!s.preview) return s;
      const prevVal = s.preview.data?.[field];
      const nextData = { ...s.preview.data, [field]: value };
      const nextMissing = (s.preview.missing || []).filter((m) => m !== field || (value == null || value === ""));
      // Fire-and-forget correction log for admin/responsable
      if (capabilities.canCreateSale && String(prevVal ?? "") !== String(value ?? "")) {
        api.post("/ai/corrections", {
          field,
          ai_value: prevVal == null ? "" : String(prevVal),
          corrected_value: String(value ?? ""),
          context: { intent: s.preview.intent },
        }).catch(() => {});
      }
      return { ...s, preview: { ...s.preview, data: nextData, missing: nextMissing } };
    });
  };

  const pickCamera = () => { try { cameraRef.current?.click(); } catch (_) {} };
  const pickFiles = () => { try { filesRef.current?.click(); } catch (_) {} };
  const onFilesSelected = async (fs) => {
    if (!fs || !fs.length) return;
    try {
      const arr = Array.from(fs);
      // Compress images >1MB to avoid loading huge iPhone photos in memory
      const compressed = await Promise.all(arr.map(async (f) => (f.size > 1_000_000 && f.type.startsWith("image/") ? compressImage(f) : f)));
      setAttachments((prev) => [...prev, ...compressed]);
      setMode("chat");
    } catch (_) {
      toast.error("Impossible d'ouvrir ce fichier. Réessayez.");
    }
  };
  const removeAttachment = (idx) => setAttachments((prev) => prev.filter((_, i) => i !== idx));

  // Send: unified handler. If a preview is waiting for missing fields, treat short input as field-fill.
  const send = async (text) => {
    if (loading) return;
    const q = (text ?? input).trim();
    if (!q && attachments.length === 0) return;

    // 1) Field-fill mode — active only in "action"-like conversation with a preview + missing fields.
    //    "commercial" est ignoré : il est optionnel et ne doit jamais bloquer la validation.
    const allMissing = state.preview && state.preview.missing ? state.preview.missing : [];
    // First missing field (regardless of blocking status) — chat answer maps to it
    if (state.preview && allMissing.length > 0 && attachments.length === 0) {
      const field = allMissing[0];
      const value = parseFieldAnswer(field, q);
      if (value !== null && value !== undefined && value !== "") {
        setInput("");
        pushMessage({ role: "user", content: q });
        const nextData = { ...state.preview.data, [field]: value };
        const nextMissing = state.preview.missing.filter((m) => m !== field);
        setState((s) => ({
          ...s,
          messages: [...s.messages, { role: "assistant", content: `${labelFor(field)} ajouté : ${q} ✅` }],
          preview: {
            ...s.preview,
            data: nextData,
            missing: nextMissing,
            confidence: nextMissing.length === 0 ? "high" : s.preview.confidence,
          },
        }));
        return;
      }
      // If we couldn't parse: fall through to normal AI so user can rephrase
    }

    setInput("");
    const filesSnap = attachments.slice();
    setAttachments([]);
    pushMessage({ role: "user", content: q, files: filesSnap });
    setLoading(true);
    try {
      let data;
      if (filesSnap.length > 0) {
        const fd = new FormData();
        fd.append("message", q || "");
        for (const f of filesSnap) fd.append("files", f);
        const res = await withTimeout(api.post("/ai/chat-multipart", fd, {
          headers: { "Content-Type": "multipart/form-data" }, timeout: AI_TIMEOUT_MS,
        }));
        data = res.data;
      } else if (mode === "action") {
        const res = await withTimeout(api.post("/ai/action", { message: q }, { timeout: AI_TIMEOUT_MS }));
        data = { preview: res.data, reply: null };
      } else {
        const res = await withTimeout(api.post("/ai/chat", { message: q }, { timeout: AI_TIMEOUT_MS }));
        data = res.data;
      }

      if (data.preview) {
        // Merge into existing draft if same intent — keep already-filled fields
        setState((s) => {
          const existing = s.preview && s.preview.intent === data.preview.intent ? s.preview.data : {};
          const merged = { ...existing, ...Object.fromEntries(Object.entries(data.preview.data || {}).filter(([, v]) => v != null && v !== "")) };
          const missing = (data.preview.missing || []).filter((k) => !merged[k]);
          return {
            ...s,
            messages: data.reply ? [...s.messages, { role: "assistant", content: data.reply }] : s.messages,
            preview: { ...data.preview, data: merged, missing },
          };
        });
      } else {
        pushMessage({ role: "assistant", content: data.reply || "Ok." });
      }
    } catch (err) {
      const msg = formatApiError(err) || err.message || "Erreur";
      pushMessage({ role: "assistant", content: `Désolé, une erreur est survenue : ${msg}` });
    } finally { setLoading(false); }
  };

  const openPrefilledSale = useCallback((preview) => {
    setExecuting(true);
    try {
      const d = preview.data || {};
      const total_ht = d.total_ht != null ? d.total_ht : null;
      const payload = {
        client_id: d.client_id || null,
        client_name: d.client_name || null,
        new_client: d.client_id ? null : ({
          name: d.client_name || "",
          phone: d.client_phone || "",
          address: d.client_address || "",
          postal_code: d.client_postal_code || "",
          city: d.client_city || "",
        }),
        bdc: d.bdc || "",
        service: d.service || "",
        amount: d.amount || total_ht || 0,
        commercial: d.commercial || "",
        sale_date: d.sale_date || "",
        source: d.source || "",
      };
      try { sessionStorage.setItem("kylot_prefill_sale", JSON.stringify(payload)); } catch (_) {}
      // Dispatch event too — Sales.jsx listens both to sessionStorage on mount AND to this event
      try { window.dispatchEvent(new CustomEvent("kylot:open-new-sale", { detail: payload })); } catch (_) {}
      setState((s) => ({
        ...s,
        messages: [...s.messages, { role: "done", content: { label: "Fiche vente ouverte", followUp: "Vérifiez les informations puis validez.", preview } }],
        preview: null,
      }));
      nav("/ventes");
    } catch (_) {
      toast.error("Impossible d'ouvrir la fiche. Réessayez.");
    } finally { setExecuting(false); }
  }, [nav]);

  const confirmAction = async (preview) => {
    if (preview.intent === "create_sale") { openPrefilledSale(preview); return; }
    // Other intents → existing execute endpoint
    setExecuting(true);
    try {
      const { data } = await withTimeout(api.post("/ai/action/execute", { intent: preview.intent, data: preview.data }, { timeout: AI_TIMEOUT_MS }));
      const label = preview.intent === "create_client" ? "Client créé" : preview.intent === "update_sale_status" ? "Statut mis à jour" : "Action effectuée";
      toast.success(`${label} ✓`);
      setState((s) => ({
        ...s,
        messages: [...s.messages, { role: "done", content: { label, followUp: "Rafraîchis la page pour voir le changement.", id: data.id } }],
        preview: null,
      }));
    } catch (err) { toast.error(formatApiError(err)); }
    finally { setExecuting(false); }
  };

  const cancelAction = () => {
    setState((s) => ({
      ...s,
      messages: [...s.messages, { role: "assistant", content: "Brouillon annulé." }],
      preview: null,
    }));
  };

  const clearConversation = () => {
    setState({ messages: [], preview: null });
    setAttachments([]);
    try { sessionStorage.removeItem(DRAFT_KEY); } catch (_) {}
  };

  const suggestions = mode === "chat" ? CHAT_SUGGESTIONS : ACTION_SUGGESTIONS;

  // Auto-widen the panel when a rich preview is shown
  const hasRichPreview = !!state.preview && state.preview.intent === "create_sale";
  const panelWidth = hasRichPreview ? "w-[460px] max-w-[95vw]" : "w-[400px] max-w-[92vw]";

  return (
    <>
      <button
        onClick={() => setOpen((v) => !v)}
        data-testid="ai-helper-btn"
        className="fixed bottom-5 right-5 z-40 h-14 w-14 rounded-full bg-[#0b0d13] text-white shadow-xl grid place-items-center hover:scale-105 transition-transform ring-1 ring-white/10 overflow-hidden"
        aria-label="Ouvrir l'assistant KIK'S"
        title="KIK'S — Assistant IA"
      >
        {open ? <X size={22} /> : <KiksAvatar size={56} ringed={false} className="!ring-0 !shadow-none" />}
      </button>

      {open && (
        <div className={`fixed bottom-24 right-5 z-40 ${panelWidth} h-[560px] max-h-[80vh] bg-white rounded-2xl shadow-2xl border border-slate-200 flex flex-col overflow-hidden transition-[width]`} data-testid="ai-helper-panel">
          <div className="p-3 border-b border-slate-200 bg-slate-900 text-white shrink-0">
            <div className="flex items-center gap-2.5">
              <KiksAvatar size={36} />
              <div className="flex-1 min-w-0">
                <div className="font-display font-semibold" data-testid="ai-helper-title">Assistant KIK'S</div>
                <div className="text-[11px] text-white/70 truncate">{listening ? "🎙️ Écoute en cours…" : (mode === "action" ? "Prépare une vente, un client, un statut" : "Analyse un devis, réponds à une question")}</div>
              </div>
              {(state.messages.length > 0 || state.preview) && (
                <button onClick={clearConversation} className="text-[10px] text-white/60 hover:text-white px-2 py-1 rounded border border-white/10 hover:border-white/30" data-testid="ai-clear">
                  Effacer
                </button>
              )}
            </div>
            <div className="flex gap-1 mt-2 bg-white/10 rounded-lg p-0.5">
              <button onClick={() => setMode("action")} data-testid="ai-mode-action" className={`flex-1 h-7 text-[11px] rounded-md flex items-center justify-center gap-1 transition ${mode === "action" ? "bg-white text-slate-900 font-medium" : "text-white/80 hover:text-white"}`}>
                <Sparkles size={11} /> Action
              </button>
              <button onClick={() => setMode("chat")} data-testid="ai-mode-chat" className={`flex-1 h-7 text-[11px] rounded-md flex items-center justify-center gap-1 transition ${mode === "chat" ? "bg-white text-slate-900 font-medium" : "text-white/80 hover:text-white"}`}>
                <MessageSquare size={11} /> Aide
              </button>
            </div>
          </div>

          <div ref={listRef} className="flex-1 overflow-y-auto overscroll-contain p-3 space-y-2 bg-slate-50/60">
            {state.messages.length === 0 && !state.preview && (
              <>
                <p className="text-xs text-slate-600 leading-relaxed">
                  {mode === "action"
                    ? "Décris une vente, joins une photo de devis, ou dis « Analyse ce devis »."
                    : "Pose une question sur l'appli, ou joins une photo/PDF."}
                </p>
                <div className="flex flex-col gap-1.5 mt-2">
                  {suggestions.map((s) => (
                    <button key={s} onClick={() => send(s)} className="text-xs px-3 py-2 rounded-lg bg-white border border-slate-200 hover:border-slate-400 hover:bg-slate-50 text-slate-700 text-left" data-testid={`ai-suggest-${mode}`}>
                      {s}
                    </button>
                  ))}
                </div>
              </>
            )}
            {state.messages.map((m, i) => {
              if (m.role === "user") return (
                <div key={i} className="flex justify-end">
                  <div className="max-w-[85%] space-y-1">
                    {m.files && m.files.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 justify-end">
                        {m.files.map((f, k) => {
                          const url = f && f.type?.startsWith("image/") ? URL.createObjectURL(f) : null;
                          return url ? (
                            <img key={k} src={url} alt="" className="h-16 w-16 object-cover rounded-md border border-slate-300" />
                          ) : (
                            <div key={k} className="text-[10px] px-2 py-1 rounded-md bg-slate-100 text-slate-700 border border-slate-200 flex items-center gap-1"><FileText size={11} />{(f && f.name) || "fichier"}</div>
                          );
                        })}
                      </div>
                    )}
                    {m.content && <div className="rounded-2xl px-3 py-2 text-sm bg-slate-900 text-white whitespace-pre-wrap break-words">{m.content}</div>}
                  </div>
                </div>
              );
              if (m.role === "done") return (
                <div key={i} className="flex justify-start">
                  <div className="max-w-[95%] w-full bg-emerald-50 border border-emerald-200 rounded-xl p-2.5 text-xs text-emerald-900 flex items-center gap-2">
                    <Check size={14} className="text-emerald-700 shrink-0" />
                    <span className="flex-1">{m.content.label} — {m.content.followUp}</span>
                  </div>
                </div>
              );
              return (
                <div key={i} className="flex justify-start">
                  <div className="max-w-[85%] rounded-2xl px-3 py-2 text-sm bg-white border border-slate-200 text-slate-800 whitespace-pre-wrap break-words">{m.content}</div>
                </div>
              );
            })}
            {state.preview && (
              <div className="flex justify-start">
                <div className="max-w-[98%] w-full">
                  <ActionPreviewCard preview={state.preview} executing={executing} capabilities={capabilities}
                    onConfirm={() => confirmAction(state.preview)}
                    onCancel={cancelAction}
                    onFieldUpdate={updatePreviewField}
                  />
                </div>
              </div>
            )}
            {loading && (
              <div className="flex justify-start">
                <div className="bg-white border border-slate-200 rounded-2xl px-3 py-2 text-sm text-slate-500 flex items-center gap-2">
                  <Loader2 size={13} className="animate-spin" /> {attachments.length > 0 || (state.messages.slice(-1)[0]?.files?.length ?? 0) > 0 ? "Analyse du document…" : "Réflexion…"}
                </div>
              </div>
            )}
          </div>

          <form onSubmit={(e) => { e.preventDefault(); send(); }} className="p-2.5 border-t border-slate-200 space-y-2 shrink-0 bg-white">
            {state.preview && state.preview.missing && state.preview.missing.filter((m) => m !== "commercial").length > 0 && (
              <div className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-2 py-1.5">
                {questionFor(state.preview.missing.filter((m) => m !== "commercial")[0])}
              </div>
            )}
            {attachments.length > 0 && (
              <div className="flex flex-wrap gap-1.5" data-testid="ai-attachments">
                {attachments.map((f, i) => {
                  const url = f.type?.startsWith("image/") ? URL.createObjectURL(f) : null;
                  return (
                    <div key={i} className="relative">
                      {url ? (
                        <img src={url} alt={f.name} className="h-14 w-14 object-cover rounded-md border border-slate-200" />
                      ) : (
                        <div className="h-14 min-w-[64px] px-2 rounded-md bg-slate-100 border border-slate-200 flex items-center gap-1 text-[10px] text-slate-700"><FileText size={12} />{(f.name || "").slice(0, 12)}</div>
                      )}
                      <button type="button" onClick={() => removeAttachment(i)} className="absolute -top-1 -right-1 bg-white rounded-full border border-slate-200 shadow-sm p-0.5" aria-label="Retirer">
                        <X size={10} className="text-red-600" />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
            <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => { onFilesSelected(e.target.files); e.target.value = ""; }} data-testid="ai-camera-input" />
            <input ref={filesRef} type="file" accept="image/*,application/pdf" multiple className="hidden" onChange={(e) => { onFilesSelected(e.target.files); e.target.value = ""; }} data-testid="ai-files-input" />
            <div className="flex gap-2">
              <div className="flex gap-1">
                <button type="button" onClick={pickCamera} className="h-10 w-10 rounded-md border border-slate-200 text-slate-500 grid place-items-center hover:bg-slate-50" aria-label="Prendre une photo" data-testid="ai-camera-btn"><ImageIcon size={15} /></button>
                <button type="button" onClick={pickFiles} className="h-10 w-10 rounded-md border border-slate-200 text-slate-500 grid place-items-center hover:bg-slate-50" aria-label="Joindre un fichier" data-testid="ai-attach-btn"><Paperclip size={15} /></button>
              </div>
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={listening ? "🎙️ Écoute en cours…" : (state.preview?.missing?.length ? "Réponds courtement…" : (attachments.length ? "Ex: Analyse ce devis, remplis la vente…" : (mode === "action" ? "Ex: Vente Kilian 5000€ 20% chez Dupont R1" : "Votre question…")))}
                className="flex-1 h-10 px-3 rounded-md border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"
                data-testid="ai-input"
              />
              {/* iter69 : dictée vocale via SpeechRecognition (Web Speech API) — mobile-first, transcription live */}
              {speechSupported && (
                <button
                  type="button"
                  onClick={toggleDictation}
                  aria-label={listening ? "Arrêter la dictée" : "Dicter à KIK'S"}
                  title={listening ? "Arrêter la dictée" : "Dicter à KIK'S"}
                  className={`h-10 w-10 rounded-md grid place-items-center transition ${listening ? "bg-red-600 text-white animate-pulse" : "border border-slate-200 text-slate-500 hover:bg-slate-50"}`}
                  data-testid="ai-dictate-btn"
                >
                  {listening ? <MicOff size={15} /> : <Mic size={15} />}
                </button>
              )}
              <button type="submit" disabled={loading || (!input.trim() && attachments.length === 0)} className="h-10 w-10 rounded-md bg-slate-900 text-white grid place-items-center disabled:opacity-50" data-testid="ai-send-btn">
                <Send size={15} />
              </button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}

const labelFor_LEGACY_UNUSED = (f) => ({
  commercial: "Commercial",
  client_name: "Client",
  amount: "Montant",
  commission_rate: "Commission",
  sale_date: "Date",
  payment_method: "Règlement",
  bdc: "N° devis",
  client_phone: "Téléphone",
  status: "Statut",
}[f] || f);

const questionFor_LEGACY_UNUSED = (f) => ({
  commercial: "Commercial manquant. Quel est le commercial ?",
  client_name: "Client manquant. Quel est le nom du client ?",
  amount: "Montant manquant. Quel est le montant ?",
  commission_rate: "Commission manquante. Quel taux ? (ex : 15%)",
  sale_date: "Date manquante. Quelle date ? (JJ/MM/AAAA)",
  payment_method: "Règlement manquant. (Chèque / Comptant / Financement / Prélèvement / RAC)",
  bdc: "N° de devis manquant. Quel est le numéro ?",
  client_phone: "Téléphone manquant. Quel numéro ?",
  status: "Statut manquant. (En cours / Argent récupéré…)",
}[f] || `Réponds pour compléter : ${f}`);
