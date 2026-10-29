// Permissions helpers — mirror of the backend RBAC model.

const SCOPE_ORDER = { none: 0, own: 1, team: 2, all: 3 };

export function canPerm(user, resource, action, minScope = "own") {
  if (!user) return false;
  if (user.role === "super_admin") return true;
  const perms = user.permissions || {};
  const v = (perms[resource] || {})[action];
  if (typeof v === "boolean") return v;
  if (typeof v === "string") {
    return (SCOPE_ORDER[v] ?? 0) >= (SCOPE_ORDER[minScope] ?? 1);
  }
  return false;
}

export function permScope(user, resource, action) {
  if (!user) return "none";
  if (user.role === "super_admin") return "all";
  const v = ((user.permissions || {})[resource] || {})[action];
  if (typeof v === "string") return v;
  if (typeof v === "boolean") return v ? "all" : "none";
  return "none";
}

// Static preview of default role-based permissions (used to reset in UI).
export const ROLE_LABELS = {
  admin: "Administrateur / Dirigeant",
  responsable: "Responsable",
  commercial: "Commercial",
  technicien: "Technicien",
  comptable: "Comptable",
  prospecteur: "Prospecteur",
  responsable_prospecteur: "Responsable prospecteur",
  super_admin: "Super-admin",
};

export const RESOURCES = [
  {
    key: "sales",
    label: "Ventes",
    actions: [
      { key: "view", label: "Voir", type: "scope" },
      { key: "create", label: "Créer", type: "bool" },
      { key: "edit", label: "Modifier", type: "bool" },
      { key: "delete", label: "Supprimer", type: "bool" },
    ],
  },
  {
    key: "stock",
    label: "Stock",
    actions: [
      { key: "view", label: "Accès à la rubrique", type: "bool" },
      { key: "view_own", label: "Voir son stock", type: "bool" },
      { key: "view_others", label: "Voir les stocks des autres techniciens", type: "bool" },
      { key: "view_company", label: "Voir le stock société", type: "bool" },
      { key: "edit", label: "Modifier / transférer", type: "bool" },
    ],
  },
  {
    key: "clients",
    label: "Clients",
    actions: [
      { key: "view", label: "Voir", type: "scope" },
      { key: "create", label: "Créer", type: "bool" },
      { key: "edit", label: "Modifier", type: "bool" },
      { key: "delete", label: "Supprimer", type: "bool" },
    ],
  },
  {
    key: "projects",
    label: "Chantiers",
    actions: [
      { key: "view", label: "Voir", type: "scope" },
      { key: "create", label: "Créer", type: "bool" },
      { key: "edit", label: "Modifier", type: "bool" },
      { key: "delete", label: "Supprimer", type: "bool" },
    ],
  },
  {
    key: "planning",
    label: "Planning",
    actions: [
      { key: "view", label: "Voir", type: "scope" },
      { key: "edit", label: "Modifier", type: "scope" },
    ],
  },
  {
    key: "commissions",
    label: "Commissions",
    actions: [
      { key: "view", label: "Voir", type: "scope" },
      { key: "edit", label: "Marquer payé", type: "bool" },
    ],
  },
  {
    key: "overtime",
    label: "Heures sup.",
    actions: [
      { key: "declare", label: "Déclarer", type: "bool" },
      { key: "view", label: "Voir", type: "scope" },
      { key: "edit", label: "Modifier", type: "bool" },
      { key: "validate", label: "Valider", type: "bool" },
    ],
  },
  {
    key: "reports",
    label: "Rapports",
    actions: [{ key: "view", label: "Voir", type: "bool" }],
  },
  {
    key: "financial",
    label: "Informations financières",
    actions: [{ key: "view", label: "Voir", type: "bool" }],
  },
  {
    key: "users",
    label: "Utilisateurs",
    actions: [{ key: "manage", label: "Gérer", type: "bool" }],
  },
  {
    key: "settings",
    label: "Paramètres",
    actions: [{ key: "modify", label: "Modifier", type: "bool" }],
  },
  {
    key: "photos",
    label: "Photos chantier",
    actions: [
      { key: "view", label: "Voir", type: "bool" },
      { key: "add", label: "Ajouter / Supprimer", type: "bool" },
    ],
  },
];

export const SCOPE_OPTIONS = [
  { value: "none", label: "Aucun" },
  { value: "own", label: "Ses données" },
  { value: "team", label: "Son équipe" },
  { value: "all", label: "Tout" },
];
