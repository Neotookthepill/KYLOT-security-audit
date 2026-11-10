/**
 * Recherche d'adresse française via l'API publique adresse.data.gouv.fr.
 * Utilisée pour compléter le code postal ou la ville sans faire perdre la
 * saisie manuelle à l'utilisateur.
 */

const clean = (value) => String(value || "").trim();

async function search(query, type = "municipality") {
  const q = clean(query);
  if (!q) return null;
  try {
    const res = await fetch(
      `https://api-adresse.data.gouv.fr/search/?q=${encodeURIComponent(q)}&type=${type}&limit=1`,
    );
    if (!res.ok) return null;
    const data = await res.json();
    return data?.features?.[0]?.properties || null;
  } catch (_) {
    return null;
  }
}

export async function lookupCityFromPostalCode(postalCode) {
  const cp = clean(postalCode);
  if (!/^\d{5}$/.test(cp)) return null;
  const city = await search(cp);
  return city?.city || null;
}

export async function lookupPostalCodeFromCity(city) {
  const name = clean(city);
  if (name.length < 2) return null;
  const row = await search(name);
  return row?.postcode || null;
}

export function mapsUrl(address, postalCode, city) {
  const q = [address, postalCode, city].map(clean).filter(Boolean).join(" ");
  if (!q) return null;
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}`;
}
