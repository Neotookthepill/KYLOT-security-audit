/**
 * Qylot workflow contracts.
 *
 * Phase 0 : lecture seule. Aucun écran ne dépend encore de ce fichier.
 * Objectif : une seule définition des phases, invariants et capacités.
 *
 * Les statuts de vente restent configurables : on ne force pas un graphe
 * rigide, on expose une phase et des capacités dérivées.
 */

export const SALE_PHASES = Object.freeze({
  pending_finance: { label: "En attente financement", terminal: false, active: true, commissionable: true, countsCA: true },
  pending_schedule: { label: "À planifier", terminal: false, active: true, commissionable: true, countsCA: true },
  in_progress: { label: "En cours", terminal: false, active: true, commissionable: true, countsCA: true },
  work_done: { label: "Travaux terminés", terminal: false, active: true, commissionable: true, countsCA: true },
  pending_cheque: { label: "Chèque à récupérer", terminal: false, active: true, commissionable: true, countsCA: true },
  paid: { label: "Encaissé", terminal: true, active: false, commissionable: true, countsCA: true },
  dispute: { label: "Litige", terminal: true, active: false, commissionable: false, countsCA: false },
  cancelled: { label: "Annulé", terminal: true, active: false, commissionable: false, countsCA: false },
  non_financable: { label: "Non finançable", terminal: true, active: false, commissionable: false, countsCA: true },
  unknown: { label: "Statut personnalisé", terminal: false, active: true, commissionable: true, countsCA: true },
});

const DEFAULT_SALE_PHASE = Object.freeze({
  attente_fi: "pending_finance",
  attente_prog: "pending_schedule",
  en_cours: "in_progress",
  chantier_fini: "work_done",
  commercial_cheque: "pending_cheque",
  argent_recupere: "paid",
  virement_recu: "paid",
  litige: "dispute",
  annule: "cancelled",
  non_financable: "non_financable",
});

/**
 * @param {string} status
 * @param {Record<string, string>} [overrides] statuts personnalisés → phase
 */
export function salePhase(status, overrides = {}) {
  const key = String(status || "");
  return overrides[key] || DEFAULT_SALE_PHASE[key] || "unknown";
}

export function salePhaseMeta(status, overrides) {
  return SALE_PHASES[salePhase(status, overrides)] || SALE_PHASES.unknown;
}

export const isSaleActive = (status, overrides) => salePhaseMeta(status, overrides).active;
export const isSaleTerminal = (status, overrides) => salePhaseMeta(status, overrides).terminal;
export const isSaleCommissionable = (status, overrides) => salePhaseMeta(status, overrides).commissionable;
export const isSaleCountedInCA = (status, overrides) => salePhaseMeta(status, overrides).countsCA;
export const isSalePaid = (status) => salePhase(status) === "paid";

/**
 * Le chantier a des états stables ; `cancelled` reste un champ séparé.
 */
export const PROJECT_STATES = Object.freeze({
  a_planifier: { label: "À planifier", terminal: false, active: true },
  en_cours: { label: "En cours", terminal: false, active: true },
  termine: { label: "À encaisser", terminal: false, active: false },
  encaisse: { label: "Encaissé", terminal: true, active: false },
  cancelled: { label: "Annulé", terminal: true, active: false },
});

export const PROJECT_TRANSITIONS = Object.freeze({
  a_planifier: ["en_cours", "cancelled"],
  en_cours: ["a_planifier", "termine", "cancelled"],
  termine: ["en_cours", "encaisse", "cancelled"],
  encaisse: [],
  cancelled: [],
});

export function projectState(project) {
  if (project?.cancelled) return "cancelled";
  const status = String(project?.status || "a_planifier");
  return PROJECT_STATES[status] ? status : "a_planifier";
}

export const canProjectTransition = (from, to) =>
  Boolean(PROJECT_TRANSITIONS[projectState({ status: from })]?.includes(to));

export const COMMISSION_STATES = Object.freeze([
  "cancelled",
  "not_eligible",
  "deferred",
  "to_pay",
  "paid",
]);

/**
 * @param {{status?: string, commission_paid?: boolean, commission_month?: string}} sale
 * @param {{saleMonth?: string, deferred?: boolean}} [options]
 */
export function commissionState(sale, options = {}) {
  if (!isSaleActive(sale?.status) && !isSaleCommissionable(sale?.status)) return "cancelled";
  if (!isSaleCommissionable(sale?.status)) return "not_eligible";
  if (options.deferred) return "deferred";
  if (sale?.commission_paid === true) return "paid";
  return "to_pay";
}

export const CHALLENGE_STATES = Object.freeze({
  upcoming: { label: "À venir", editable: true },
  active: { label: "En cours", editable: true },
  closed: { label: "Terminé", editable: false },
  archived: { label: "Archivé", editable: false },
});

export function challengeState(challenge, now = new Date()) {
  if (challenge?.archived_at) return "archived";
  if (challenge?.closed_at) return "closed";
  const start = challenge?.start_date ? new Date(`${challenge.start_date}T00:00:00`) : null;
  const end = challenge?.end_date ? new Date(`${challenge.end_date}T23:59:59`) : null;
  if (start && now < start) return "upcoming";
  if (end && now > end) return "closed";
  return "active";
}

export const canEditChallenge = (challenge, now) =>
  CHALLENGE_STATES[challengeState(challenge, now)]?.editable === true;

export const SYNC_STATES = Object.freeze({
  idle: "idle",
  pending: "pending",
  offline: "offline",
  syncing: "syncing",
  conflict: "conflict",
  error: "error",
});

export function syncState({ online = true, pending = 0, syncing = false, conflict = null, lastError = null } = {}) {
  if (conflict) return "conflict";
  if (!online) return "offline";
  if (syncing) return "syncing";
  if (lastError) return "error";
  if (pending > 0) return "pending";
  return "idle";
}

export const AUTH_STATES = Object.freeze([
  "loading",
  "anonymous",
  "mfa_required",
  "mfa_setup_required",
  "mfa_grace",
  "authenticated",
  "expired",
]);

export const FORM_STATES = Object.freeze({
  idle: "idle",
  dirty: "dirty",
  submitting: "submitting",
  success: "success",
  error: "error",
});

export const canSubmit = ({ dirty = false, submitting = false } = {}) => dirty && !submitting;
export const canClose = ({ submitting = false } = {}) => !submitting;
