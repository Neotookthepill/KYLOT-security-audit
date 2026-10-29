// Central helper for sale statuses (labels + Tailwind classes)
// Order below = QYLOT default (top → bottom). Companies can override via
// settings.sale_status_order (list of values consumed by orderStatuses()) OR
// via the full sale_statuses array (from GET /api/sale-statuses) — see iter40.

// Tailwind palette allowed by backend (must match ALLOWED_STATUS_COLORS).
export const STATUS_COLORS = [
  { key: "slate", label: "Ardoise", dot: "bg-slate-500" },
  { key: "red", label: "Rouge", dot: "bg-red-500" },
  { key: "orange", label: "Orange", dot: "bg-orange-500" },
  { key: "amber", label: "Ambre", dot: "bg-amber-500" },
  { key: "yellow", label: "Jaune", dot: "bg-yellow-500" },
  { key: "lime", label: "Lime", dot: "bg-lime-500" },
  { key: "green", label: "Vert", dot: "bg-green-500" },
  { key: "emerald", label: "Émeraude", dot: "bg-emerald-500" },
  { key: "teal", label: "Sarcelle", dot: "bg-teal-500" },
  { key: "cyan", label: "Cyan", dot: "bg-cyan-500" },
  { key: "sky", label: "Ciel", dot: "bg-sky-500" },
  { key: "blue", label: "Bleu", dot: "bg-blue-500" },
  { key: "indigo", label: "Indigo", dot: "bg-indigo-500" },
  { key: "violet", label: "Violet", dot: "bg-violet-500" },
  { key: "purple", label: "Pourpre", dot: "bg-purple-500" },
  { key: "fuchsia", label: "Fuchsia", dot: "bg-fuchsia-500" },
  { key: "pink", label: "Rose", dot: "bg-pink-500" },
  { key: "rose", label: "Rose fonce", dot: "bg-rose-500" },
];

// Tailwind safelist — required to force JIT to include these classes at build time.
// Any color used in dynamic clsFromColor() MUST appear as a literal string somewhere.
// eslint-disable-next-line no-unused-vars
const _TW_SAFELIST_STATUS = [
  "bg-slate-100 text-slate-800",
  "bg-red-100 text-red-800",
  "bg-orange-100 text-orange-800",
  "bg-amber-100 text-amber-800",
  "bg-yellow-100 text-yellow-900",
  "bg-lime-100 text-lime-800",
  "bg-green-100 text-green-800",
  "bg-emerald-100 text-emerald-800",
  "bg-teal-100 text-teal-800",
  "bg-cyan-100 text-cyan-800",
  "bg-sky-100 text-sky-800",
  "bg-blue-100 text-blue-800",
  "bg-indigo-100 text-indigo-800",
  "bg-violet-100 text-violet-800",
  "bg-purple-100 text-purple-800",
  "bg-fuchsia-100 text-fuchsia-800",
  "bg-pink-100 text-pink-800",
  "bg-rose-100 text-rose-800",
];
export const clsFromColor = (color) => {
  const c = STATUS_COLORS.some((x) => x.key === color) ? color : "slate";
  const text = c === "yellow" ? "text-yellow-900" : `text-${c}-800`;
  return `bg-${c}-100 ${text}`;
};

// Fallback defaults (aligned with backend DEFAULT_SALE_STATUSES). Used until /api/sale-statuses resolves.
export const SALE_STATUSES = [
  { value: "attente_prog", label: "En attente prog", color: "violet", cls: clsFromColor("violet") },
  { value: "attente_fi", label: "En attente FI", color: "orange", cls: clsFromColor("orange") },
  { value: "en_cours", label: "PROG", color: "indigo", cls: clsFromColor("indigo") },
  { value: "chantier_fini", label: "Chantier fini", color: "yellow", cls: clsFromColor("yellow") },
  { value: "commercial_cheque", label: "Commercial a le chèque", color: "sky", cls: clsFromColor("sky") },
  { value: "argent_recupere", label: "Chèque récupéré", color: "emerald", cls: clsFromColor("emerald") },
  { value: "litige", label: "Litige", color: "orange", cls: clsFromColor("orange") },
  { value: "annule", label: "Annulé", color: "red", cls: clsFromColor("red") },
];

export const STATUS_MAP = SALE_STATUSES.reduce((acc, s) => { acc[s.value] = s; return acc; }, {});

// iter124 : construit une liste ordonnée + un map à partir du payload complet
// renvoyé par GET /api/sale-statuses (inclut les statuts CUSTOM ajoutés par l'admin).
// Chaque item du payload a { value, label, color, active, default, system, hides_from_projects }.
// Renvoie [{ value, label, color, cls, active, default, system, hides_from_projects }].
export const resolveStatusesFromPayload = (payload) => {
  if (!Array.isArray(payload) || payload.length === 0) return SALE_STATUSES;
  return payload
    .filter((s) => s && s.value)
    .map((s) => ({
      value: s.value,
      label: s.label || s.value,
      color: s.color || "slate",
      cls: clsFromColor(s.color || "slate"),
      active: s.active !== false,
      default: !!s.default,
      system: !!s.system,
      hides_from_projects: !!s.hides_from_projects,
    }));
};
export const buildStatusMap = (list) => (Array.isArray(list) ? list : SALE_STATUSES).reduce((acc, s) => { acc[s.value] = s; return acc; }, {});

// Reorder SALE_STATUSES using a per-company order (list of values). Unknown / missing values
// are appended in their original order at the end.
export const orderStatuses = (order) => {
  if (!Array.isArray(order) || order.length === 0) return SALE_STATUSES;
  const seen = new Set();
  const ordered = [];
  for (const v of order) {
    const s = STATUS_MAP[v];
    if (s && !seen.has(v)) { ordered.push(s); seen.add(v); }
  }
  for (const s of SALE_STATUSES) {
    if (!seen.has(s.value)) ordered.push(s);
  }
  return ordered;
};

export const COMMISSION_RATES = [0, 0.10, 0.13, 0.15, 0.20, 0.25, 0.30];
export const formatRate = (r) => `${Math.round((r || 0) * 100)} %`;

export const PAYMENT_OPTIONS = [
  { value: "cheque", label: "Chèque" },
  { value: "virement", label: "Virement" },
  { value: "cb", label: "Carte bancaire" },
  { value: "financement", label: "Financement" },
  { value: "acompte", label: "Acompte + solde" },
  { value: "rac", label: "RAC" },
];
export const PAYMENT_LABELS = { comptant: "Comptant", ...PAYMENT_OPTIONS.reduce((acc, p) => { acc[p.value] = p.label; return acc; }, {}) };
export const CHEQUE_INSTALLMENTS = [1, 2, 3, 5, 10];

// Sources de la vente
export const SOURCES = [
  { value: "R1", label: "R1", cls: "bg-blue-100 text-blue-800" },
  { value: "Assist", label: "Assist", cls: "bg-purple-100 text-purple-800" },
  { value: "CQ", label: "CQ", cls: "bg-teal-100 text-teal-800" },
  { value: "CA", label: "CA", cls: "bg-rose-100 text-rose-800" },
  { value: "TAP", label: "TAP", cls: "bg-amber-100 text-amber-800" },
  { value: "Sous-traitance", label: "Sous-traitance", cls: "bg-slate-200 text-slate-800" },
];
export const SOURCE_MAP = SOURCES.reduce((acc, s) => { acc[s.value] = s; return acc; }, {});

export const formatPayment = (method, installments, financementAmount, totalAmount) => {
  const base = PAYMENT_LABELS[method] || method || "—";
  if (method === "cheque" && installments && installments > 1) return `${base} (${installments}×)`;
  if (method === "financement" && financementAmount != null && totalAmount != null) {
    const comptant = Math.max(0, (parseFloat(totalAmount) || 0) - (parseFloat(financementAmount) || 0));
    if (comptant > 0) return `Financement ${Math.round(financementAmount)} € + Comptant ${Math.round(comptant)} €`;
  }
  return base;
};

export const computeComptantPart = (totalAmount, financementAmount) => {
  return Math.max(0, (parseFloat(totalAmount) || 0) - (parseFloat(financementAmount) || 0));
};

// Mois YYYY-MM helpers
export const currentMonth = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};

export const shiftMonth = (yyyyMM, delta) => {
  const [y, m] = yyyyMM.split("-").map(Number);
  const d = new Date(y, (m - 1) + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};

export const monthLabel = (yyyyMM) => {
  if (!yyyyMM) return "—";
  const [y, m] = yyyyMM.split("-").map(Number);
  const names = ["Janvier","Février","Mars","Avril","Mai","Juin","Juillet","Août","Septembre","Octobre","Novembre","Décembre"];
  return `${names[(m || 1) - 1]} ${y || ""}`.trim();
};
