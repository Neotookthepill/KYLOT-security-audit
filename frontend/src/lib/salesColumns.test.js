import { DEFAULT_HIDDEN_COLUMNS, SALES_COLUMNS } from "./salesColumns";

test("les colonnes ventes gardent des index uniques et stables", () => {
  const indexes = SALES_COLUMNS.map((c) => c.index);
  expect(new Set(indexes).size).toBe(indexes.length);
  expect(SALES_COLUMNS.find((c) => c.key === "client").index).toBe(4);
  expect(SALES_COLUMNS.find((c) => c.key === "amount").index).toBe(7);
});

test("les colonnes par défaut réduisent la densité sans masquer l'essentiel", () => {
  expect(DEFAULT_HIDDEN_COLUMNS).toEqual(["phone", "bdc", "source"]);
  expect(DEFAULT_HIDDEN_COLUMNS).not.toContain("client");
  expect(DEFAULT_HIDDEN_COLUMNS).not.toContain("amount");
  expect(DEFAULT_HIDDEN_COLUMNS).not.toContain("commercial");
});
