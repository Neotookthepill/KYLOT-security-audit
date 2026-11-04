// Un champ client peut contenir plusieurs numéros séparés par « / ».
// On garde le texte affiché tel quel, mais chaque numéro devient un lien tel:.
export function splitPhoneNumbers(value) {
  if (value == null) return [];
  return String(value)
    .split(/\s*\/\s*/)
    .map((part) => part.trim())
    .filter(Boolean);
}

export function phoneHref(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const dialable = raw.replace(/[^\d+]/g, "");
  if (!dialable || dialable === "+") return "";
  return `tel:${dialable}`;
}

export function hasMultiplePhones(value) {
  return splitPhoneNumbers(value).length > 1;
}
