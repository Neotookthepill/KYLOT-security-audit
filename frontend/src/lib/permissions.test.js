import { canPerm, permScope } from "./permissions";

const user = (role, permissions = {}) => ({ role, permissions });

describe("RBAC frontend helpers", () => {
  test("denies access when no user is authenticated", () => {
    expect(canPerm(null, "clients", "view")).toBe(false);
    expect(permScope(null, "clients", "view")).toBe("none");
  });

  test("super admin has all scopes", () => {
    const current = user("super_admin");
    expect(canPerm(current, "clients", "delete", "all")).toBe(true);
    expect(permScope(current, "clients", "view")).toBe("all");
  });

  test("boolean permissions are fail closed", () => {
    const current = user("commercial", { clients: { edit: false } });
    expect(canPerm(current, "clients", "edit")).toBe(false);
    expect(canPerm(current, "clients", "delete")).toBe(false);
  });

  test("own scope cannot satisfy team or all", () => {
    const current = user("commercial", { clients: { view: "own" } });
    expect(canPerm(current, "clients", "view", "own")).toBe(true);
    expect(canPerm(current, "clients", "view", "team")).toBe(false);
    expect(canPerm(current, "clients", "view", "all")).toBe(false);
  });

  test("all scope satisfies narrower scopes", () => {
    const current = user("admin", { clients: { view: "all" } });
    expect(canPerm(current, "clients", "view", "own")).toBe(true);
    expect(canPerm(current, "clients", "view", "team")).toBe(true);
    expect(canPerm(current, "clients", "view", "all")).toBe(true);
  });

  test("unknown scopes and resources are denied", () => {
    const current = user("commercial", { clients: { view: "unexpected" } });
    expect(canPerm(current, "clients", "view")).toBe(false);
    expect(canPerm(current, "sales", "view")).toBe(false);
  });
});
