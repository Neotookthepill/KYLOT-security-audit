// Formatage d'affichage uniquement. Les valeurs stockées restent en ISO.
const SPECIAL = new Set(["attente_financement", "attente_14j", "", null, undefined]);

export function formatDateFR(value, fallback = "—") {
  if (value === null || value === undefined || value === "") return fallback;
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    return value.toLocaleDateString("fr-FR");
  }
  const raw = String(value).trim();
  if (SPECIAL.has(raw)) return fallback;
  // Ne pas casser les libellés métier (ex. « décembre 2026 »).
  const m = raw.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T\s].*)?$/);
  if (m) return `${m[3]}/${m[2]}/${m[1]}`;
  // Déjà au format français : on le laisse tel quel.
  if (/^\d{2}\/\d{2}\/\d{4}/.test(raw)) return raw;
  return raw;
}

export function formatDateTimeFR(value, fallback = "—") {
  if (!value) return fallback;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return formatDateFR(value, fallback);
  return d.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

export default formatDateFR;
