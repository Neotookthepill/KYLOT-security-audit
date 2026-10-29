import React, { act } from "react";
import { createRoot } from "react-dom/client";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("@/lib/api", () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
  syncOffline: jest.fn(),
}));

jest.mock("@/lib/offline", () => ({
  clearOfflineData: jest.fn(async () => {}),
  clearSensitiveClientState: jest.fn(async () => {}),
  clearSensitiveSessionStorage: jest.fn(),
  setOfflineIdentity: jest.fn(),
}));

import mockApi, { syncOffline as mockSyncOffline } from "@/lib/api";
import {
  clearOfflineData as mockClearOfflineData,
  clearSensitiveClientState as mockClearSensitiveClientState,
  clearSensitiveSessionStorage as mockClearSensitiveSessionStorage,
  setOfflineIdentity as mockSetOfflineIdentity,
} from "@/lib/offline";
import { AuthProvider, useAuth } from "./AuthContext";

let currentAuth;
function Probe() {
  currentAuth = useAuth();
  return <div data-user={currentAuth.user?.id || "none"} data-loading={String(currentAuth.loading)} />;
}

const flush = () => act(async () => { await Promise.resolve(); await Promise.resolve(); });

describe("AuthContext session lifecycle", () => {
  let container;
  let root;

  beforeEach(() => {
    jest.clearAllMocks();
    currentAuth = null;
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
  });

  async function mountWithInitial(response) {
    response instanceof Error
      ? mockApi.get.mockRejectedValueOnce(response)
      : mockApi.get.mockResolvedValueOnce({ data: response });
    await act(async () => root.render(<AuthProvider><Probe /></AuthProvider>));
    await flush();
  }

  test("confirms server identity before starting offline replay", async () => {
    await mountWithInitial({ id: "user-a", role: "admin", permissions: {} });
    expect(mockSetOfflineIdentity).toHaveBeenCalledWith("user-a");
    expect(mockSyncOffline).toHaveBeenCalledTimes(1);
    expect(currentAuth.user.id).toBe("user-a");
    expect(currentAuth.loading).toBe(false);
  });

  test("initial authentication failure leaves no offline identity", async () => {
    await mountWithInitial(Object.assign(new Error("unauthorized"), { response: { status: 401 } }));
    expect(mockSetOfflineIdentity).toHaveBeenCalledWith(null);
    expect(currentAuth.user).toBeNull();
  });

  test("login clears the previous account cache before setting the new identity", async () => {
    await mountWithInitial({ id: "user-a", role: "admin", permissions: {} });
    mockApi.post.mockResolvedValueOnce({ data: { user: { id: "user-b", role: "commercial" } } });
    await act(async () => currentAuth.login("b@example.com", "long-password"));
    expect(mockClearOfflineData).toHaveBeenCalledTimes(1);
    expect(mockClearSensitiveSessionStorage).toHaveBeenCalledTimes(1);
    expect(mockSetOfflineIdentity).toHaveBeenLastCalledWith("user-b");
    expect(currentAuth.user.id).toBe("user-b");
  });

  test("logout purges browser state even if the server request fails", async () => {
    await mountWithInitial({ id: "user-a", role: "admin", permissions: {} });
    mockApi.post.mockRejectedValueOnce(new Error("offline"));
    await act(async () => currentAuth.logout());
    expect(mockClearSensitiveClientState).toHaveBeenCalledTimes(1);
    expect(currentAuth.user).toBeNull();
  });

  test("temporary refresh failure preserves the current confirmed user", async () => {
    await mountWithInitial({ id: "user-a", role: "admin", permissions: {} });
    mockApi.get.mockRejectedValueOnce(new Error("network"));
    await act(async () => currentAuth.refreshUser());
    expect(currentAuth.user.id).toBe("user-a");
    expect(mockSetOfflineIdentity).not.toHaveBeenLastCalledWith(null);
  });

  test("401 during refresh revokes the current identity", async () => {
    await mountWithInitial({ id: "user-a", role: "admin", permissions: {} });
    mockApi.get.mockRejectedValueOnce(Object.assign(new Error("unauthorized"), { response: { status: 401 } }));
    await act(async () => currentAuth.refreshUser());
    expect(mockSetOfflineIdentity).toHaveBeenLastCalledWith(null);
    expect(currentAuth.user).toBeNull();
  });
});
