import {
  SALE_PHASES,
  salePhase,
  isSaleActive,
  isSaleTerminal,
  isSaleCommissionable,
  isSaleCountedInCA,
  isSalePaid,
  projectState,
  canProjectTransition,
  commissionState,
  challengeState,
  canEditChallenge,
  syncState,
  canSubmit,
  canClose,
} from "./workflows";

describe("workflow contracts", () => {
  test("sale statuses are mapped to a phase", () => {
    expect(salePhase("en_cours")).toBe("in_progress");
    expect(salePhase("annule")).toBe("cancelled");
    expect(salePhase("custom_status")).toBe("unknown");
    expect(isSaleCountedInCA("custom_status")).toBe(false);
    expect(isSaleCommissionable("custom_status")).toBe(false);
  });

  test("custom statuses can declare their phase without a code change", () => {
    expect(salePhase("en_attente_client", { en_attente_client: "pending_schedule" })).toBe("pending_schedule");
  });

  test("CA and commission capabilities preserve current business rules", () => {
    expect(isSaleCountedInCA("en_cours")).toBe(true);
    expect(isSaleCountedInCA("argent_recupere")).toBe(true);
    expect(isSaleCountedInCA("annule")).toBe(false);
    expect(isSaleCommissionable("attente_fi")).toBe(true);
    expect(isSaleCommissionable("non_financable")).toBe(false);
    expect(isSalePaid("argent_recupere")).toBe(true);
    expect(isSalePaid("virement_recu")).toBe(true);
    expect(isSalePaid("en_cours")).toBe(false);
  });

  test("active, terminal and commissionable are derived from the phase", () => {
    expect(isSaleActive("en_cours")).toBe(true);
    expect(isSaleTerminal("argent_recupere")).toBe(true);
    expect(isSaleCommissionable("litige")).toBe(false);
    expect(SALE_PHASES.paid.terminal).toBe(true);
  });

  test("project cancellation is a terminal state outside status", () => {
    expect(projectState({ status: "en_cours", cancelled: true })).toBe("cancelled");
    expect(projectState({ status: "termine" })).toBe("termine");
  });

  test("project transitions keep correction paths open", () => {
    expect(canProjectTransition("a_planifier", "en_cours")).toBe(true);
    expect(canProjectTransition("termine", "en_cours")).toBe(true);
    expect(canProjectTransition("encaisse", "en_cours")).toBe(false);
    expect(canProjectTransition("en_cours", "cancelled")).toBe(true);
  });

  test("commission states distinguish paid, deferred and ineligible", () => {
    expect(commissionState({ status: "en_cours", commission_paid: true })).toBe("paid");
    expect(commissionState({ status: "en_cours" })).toBe("to_pay");
    expect(commissionState({ status: "en_cours" }, { deferred: true })).toBe("deferred");
    expect(commissionState({ status: "litige" })).toBe("cancelled");
  });

  test("challenge state is derived from dates", () => {
    const now = new Date("2026-11-09T12:00:00");
    expect(challengeState({ start_date: "2026-11-10", end_date: "2026-11-20" }, now)).toBe("upcoming");
    expect(challengeState({ start_date: "2026-11-01", end_date: "2026-11-20" }, now)).toBe("active");
    expect(challengeState({ start_date: "2026-10-01", end_date: "2026-11-01" }, now)).toBe("closed");
    expect(canEditChallenge({ closed_at: "2026-11-01" }, now)).toBe(false);
  });

  test("sync state never reports syncing with an empty queue", () => {
    expect(syncState({ pending: 0 })).toBe("idle");
    expect(syncState({ pending: 1 })).toBe("pending");
    expect(syncState({ syncing: true, pending: 1 })).toBe("syncing");
    expect(syncState({ conflict: { id: "x" } })).toBe("conflict");
    expect(syncState({ online: false })).toBe("offline");
  });

  test("form guards prevent double submit and unsafe close", () => {
    expect(canSubmit({ dirty: true })).toBe(true);
    expect(canSubmit({ dirty: true, submitting: true })).toBe(false);
    expect(canSubmit({ dirty: false })).toBe(false);
    expect(canClose({ submitting: true })).toBe(false);
  });
});
