const mockStores = new Map();

jest.mock("idb-keyval", () => ({
  createStore: (dbName) => dbName,
  get: async (key, store) => mockStores.get(store)?.get(key),
  set: async (key, value, store) => {
    if (!mockStores.has(store)) mockStores.set(store, new Map());
    mockStores.get(store).set(key, value);
  },
  del: async (key, store) => mockStores.get(store)?.delete(key),
  keys: async (store) => [...(mockStores.get(store)?.keys() || [])],
}));

import {
  cacheKey,
  clearSensitiveClientState,
  clearSensitiveSessionStorage,
  enqueue,
  isSkipped,
  setOfflineIdentity,
  syncNow,
} from "./offline";

describe("offline security boundaries", () => {
  beforeEach(async () => {
    mockStores.clear();
    sessionStorage.clear();
    setOfflineIdentity(null);
    Object.defineProperty(window.navigator, "onLine", { configurable: true, value: true });
    await clearSensitiveClientState();
  });

  test("never replays queued work before the server identity is confirmed", async () => {
    const send = jest.fn();
    await syncNow(send);
    expect(send).not.toHaveBeenCalled();
  });

  test("partitions cache keys by confirmed user", () => {
    const config = { url: "/clients", params: { page: 1 } };
    expect(cacheKey(config)).toMatch(/^unauthenticated GET /);
    setOfflineIdentity("user-a");
    expect(cacheKey(config)).toMatch(/^user-a GET /);
    setOfflineIdentity("user-b");
    expect(cacheKey(config)).toMatch(/^user-b GET /);
  });

  test("marks authentication, AI and exports as never-offline", () => {
    expect(isSkipped("/auth/me")).toBe(true);
    expect(isSkipped("/ai/chat")).toBe(true);
    expect(isSkipped("/export/sales.csv")).toBe(true);
    expect(isSkipped("/clients")).toBe(false);
  });

  test("replays a queued update only after identity confirmation", async () => {
    setOfflineIdentity("user-a");
    await enqueue({ method: "put", url: "/clients/12345678-1234-1234-1234-123456789012", data: { city: "Paris" } });
    const send = jest.fn().mockResolvedValue({ data: { ok: true } });
    await syncNow(send);
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ method: "put", data: { city: "Paris" } }));
    send.mockClear();
    await syncNow(send);
    expect(send).not.toHaveBeenCalled();
  });

  test("keeps a queued update after a 401 for a later authenticated retry", async () => {
    setOfflineIdentity("user-a");
    await enqueue({ method: "patch", url: "/clients/12345678-1234-1234-1234-123456789012", data: { city: "Lyon" } });
    await syncNow(jest.fn().mockRejectedValue({ response: { status: 401 } }));
    const retry = jest.fn().mockResolvedValue({ data: { ok: true } });
    await syncNow(retry);
    expect(retry).toHaveBeenCalledTimes(1);
  });

  test("logout cleanup removes queued data and sensitive drafts", async () => {
    setOfflineIdentity("user-a");
    await enqueue({ method: "patch", url: "/clients/12345678-1234-1234-1234-123456789012", data: { city: "Nice" } });
    sessionStorage.setItem("kylot_ai_draft_v1:user-a", "secret");
    sessionStorage.setItem("kylot_prefill_sale", "secret");
    sessionStorage.setItem("harmless", "keep");
    await clearSensitiveClientState();
    expect(sessionStorage.getItem("kylot_ai_draft_v1:user-a")).toBeNull();
    expect(sessionStorage.getItem("kylot_prefill_sale")).toBeNull();
    expect(sessionStorage.getItem("harmless")).toBe("keep");
    const send = jest.fn();
    setOfflineIdentity("user-a");
    await syncNow(send);
    expect(send).not.toHaveBeenCalled();
  });

  test("session cleanup also removes the legacy unscoped AI draft", () => {
    sessionStorage.setItem("kylot_ai_draft_v1", "secret");
    clearSensitiveSessionStorage();
    expect(sessionStorage.getItem("kylot_ai_draft_v1")).toBeNull();
  });
});
