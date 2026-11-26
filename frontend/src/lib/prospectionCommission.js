// Moteur unique des commissions de prospection.
// Il doit rester la seule source de vérité pour :
// - le palier du responsable (mois de signature) ;
// - la commission acquise ;
// - la répartition payable / reportée / en attente.
// Les pages Prospection et Commissions doivent utiliser ces fonctions,
// jamais une copie locale des règles.

export const INACTIVE_SALE_STATUSES = ["annule", "litige"];
export const saleMonth = (row) => String(row?.sale_date || "").slice(0, 7);
export const commissionMonth = (row) => {
  const raw = row?.commission_month || row?.prospect_commission_month || saleMonth(row);
  return /^\d{4}-\d{2}$/.test(String(raw || "")) ? String(raw) : saleMonth(row);
};
export const projectValidated = (row) => ["termine", "encaisse"].includes(String(row?.project_status || ""))
  || ["chantier_fini", "argent_recupere"].includes(String(row?.status || ""));
export const isActive = (row) => !INACTIVE_SALE_STATUSES.includes(row?.status) && !!saleMonth(row);

export function managerRatesFor(rows, goal = 12, below = 1, above = 2) {
  const grouped = {};
  for (const row of rows) {
    if (!isActive(row)) continue;
    const month = saleMonth(row);
    grouped[month] = grouped[month] || { count: 0, ca: 0 };
    grouped[month].count += 1;
    grouped[month].ca += parseFloat(row.amount) || 0;
  }
  return Object.fromEntries(Object.entries(grouped).map(([month, value]) => [month, {
    ...value,
    rate: value.count >= goal ? above : below,
    reached: value.count >= goal,
  }]));
}

export function managerCommissionFor(row, rates) {
  const rate = rates[saleMonth(row)]?.rate ?? 0;
  return (parseFloat(row.amount) || 0) * (rate / 100);
}

/**
 * @param {object} p
 * @param {Array} p.rows toutes les ventes, sans filtre prospecteur
 * @param {Array} p.visible ventes de la période affichée
 * @param {string} p.fromMonth premier mois de la période (YYYY-MM)
 * @param {string} p.endMonth dernier mois de la période (YYYY-MM)
 * @param {number} p.goal p.below p.above
 */
export function buildManagerSummary({ rows, visible, fromMonth, endMonth, goal = 12, below = 1, above = 2 }) {
  const activeRows = rows.filter(isActive);
  const rates = managerRatesFor(activeRows, goal, below, above);
  // Les ventes retenues sont celles SIGNÉES dans la période, même si la page
  // les affiche aussi à cause de leur mois de paiement reporté.
  const signed = visible.filter((row) => {
    if (!isActive(row)) return false;
    const month = saleMonth(row);
    return (!fromMonth || month >= fromMonth) && month <= endMonth;
  });
  const deferredRows = signed.filter((row) => commissionMonth(row) > endMonth);
  const pendingRows = signed.filter((row) => commissionMonth(row) <= endMonth && !projectValidated(row));
  const payableRows = signed.filter((row) => commissionMonth(row) <= endMonth && projectValidated(row));
  const acquired = signed.reduce((sum, row) => sum + managerCommissionFor(row, rates), 0);
  const payable = payableRows.reduce((sum, row) => sum + managerCommissionFor(row, rates), 0);
  const deferred = deferredRows.reduce((sum, row) => sum + managerCommissionFor(row, rates), 0);
  const pending = pendingRows.reduce((sum, row) => sum + managerCommissionFor(row, rates), 0);
  return {
    activeRows, rates, signedRows: signed, deferredRows, pendingRows, payableRows,
    acquired, payable, deferred, pending,
    rate: rates[saleMonth({ sale_date: `${endMonth}-01` })]?.rate ?? below,
  };
}
