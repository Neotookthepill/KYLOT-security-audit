export const SALES_COLUMNS = [
  { key: "status", label: "Statut", index: 1 },
  { key: "date", label: "Date", index: 2 },
  { key: "bdc", label: "BDC", index: 3 },
  { key: "client", label: "Client", index: 4 },
  { key: "phone", label: "Téléphone", index: 5 },
  { key: "products", label: "Produits", index: 6 },
  { key: "amount", label: "Montant HT", index: 7 },
  { key: "payment", label: "Règlement", index: 8 },
  { key: "commercial", label: "Commercial", index: 9 },
  { key: "source", label: "Source", index: 10 },
];
export const DEFAULT_HIDDEN_COLUMNS = ["phone", "bdc", "source"];
export const salesTableColumnClasses = (hidden) => (hidden || []).map((key) => `hide-${key}`).join(" ");
