jest.mock("@/lib/offline", () => ({
  cacheKey: jest.fn(() => "test-cache-key"),
  readCache: jest.fn(),
  writeCache: jest.fn(),
  enqueue: jest.fn(),
  isSkipped: jest.fn(() => false),
  syncNow: jest.fn(),
  setOnline: jest.fn(),
  refreshPending: jest.fn(),
  clearSensitiveClientState: jest.fn(),
}));

import { formatApiError } from "./api";

describe("API error normalization", () => {
  test("does not expose object coercion artifacts", () => {
    expect(formatApiError({ response: { data: { detail: { message: "Refusé" } } } })).toBe("Refusé");
    expect(formatApiError({ response: { data: { detail: { msg: "Invalide" } } } })).toBe("Invalide");
  });

  test("uses a safe generic message when no server detail exists", () => {
    expect(formatApiError({})).toBe("Une erreur est survenue");
    expect(formatApiError({ message: "Réseau indisponible" })).toBe("Réseau indisponible");
  });

  test("humanizes validation errors without rendering raw objects", () => {
    const text = formatApiError({ response: { data: { detail: [
      { loc: ["body", "sale_date"], type: "string_pattern_mismatch", msg: "String should match pattern" },
      { loc: ["body", "amount"], type: "greater_than_equal", msg: "Input should be greater than or equal to 0" },
    ] } } });
    expect(text).toContain("Date de vente");
    expect(text).toContain("Montant");
    expect(text).not.toContain("[object Object]");
  });

  test("preserves a plain server message", () => {
    expect(formatApiError({ response: { data: { detail: "Accès refusé" } } })).toBe("Accès refusé");
  });
});
