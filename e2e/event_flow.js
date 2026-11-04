#!/usr/bin/env node
/* Planning event: all roles can open details; only authorized users see edit. */
const fs = require("fs");
const { chromium } = require("playwright");
const BASE = process.env.STAGING_URL || "https://kylot-preview.onrender.com";
const env = Object.fromEntries(fs.readFileSync(process.env.E2E_ENV_FILE || "/tmp/kylot-e2e.env", "utf8")
  .split(/\r?\n/).filter(Boolean).map((line) => { const i = line.indexOf("="); return [line.slice(0, i), line.slice(i + 1)]; }));
let passed = 0; const failures = [];
function ok(label, cond, detail = "") { if (cond) { passed++; console.log(`PASS ${label}`); } else { failures.push(label); console.log(`FAIL ${label} ${detail}`.trim()); } }

async function login(context, email, password) {
  const page = await context.newPage();
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded", timeout: 120000 });
  await page.fill('[data-testid="login-email-input"]', email);
  await page.fill('[data-testid="login-password-input"]', password);
  await page.click('[data-testid="login-submit-btn"]');
  await page.waitForURL(`${BASE}/`, { timeout: 30000 });
  await context.request.post("/api/me/onboarding-complete");
  return page;
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const stamp = Date.now().toString().slice(-6);
  const title = `E2E-EVENT-${stamp}`;
  let eventId;
  try {
    const adminContext = await browser.newContext({ baseURL: BASE, viewport: { width: 1440, height: 1000 } });
    const adminPage = await login(adminContext, env.E2E_ADMIN_EMAIL, env.E2E_ADMIN_PASSWORD);
    const today = new Date().toISOString().slice(0, 10);
    const created = await adminContext.request.post("/api/events", { data: {
      title, date: today, start_time: "09:00", end_time: "10:30",
      description: "Consignes E2E : accès par le portail, prévenir le client.",
      location: "Agence de Lyon — salle 2",
      all_company: true, participants: [], show_on_dashboard: false, send_notification: false,
    }});
    eventId = (await created.json()).id;
    ok("event created with location", created.status() === 200 && Boolean(eventId), `HTTP ${created.status()}`);

    await adminPage.goto(`${BASE}/planning`, { waitUntil: "domcontentloaded" });
    await adminPage.waitForSelector(`[data-testid="cal-event-item-${eventId}"]`, { timeout: 15000 });
    await adminPage.click(`[data-testid="cal-event-item-${eventId}"]`);
    await adminPage.waitForSelector('[data-testid="event-details-dialog"]', { timeout: 10000 });
    ok("admin can open event details", true);
    const details = await adminPage.locator('[data-testid="event-details-dialog"]').innerText();
    ok("event details show description", details.includes("Consignes E2E"));
    ok("event details show location", details.includes("Agence de Lyon"));
    ok("event details show time", details.includes("09:00") && details.includes("10:30"));
    ok("admin sees edit action", (await adminPage.locator('[data-testid="event-details-edit"]').count()) === 1);
    await adminPage.click('[data-testid="event-details-close"]');

    const commercialContext = await browser.newContext({ baseURL: BASE, viewport: { width: 1440, height: 1000 } });
    const commercialPage = await login(commercialContext, env.E2E_COMMERCIAL_EMAIL, env.E2E_COMMERCIAL_PASSWORD);
    await commercialPage.goto(`${BASE}/planning`, { waitUntil: "domcontentloaded" });
    await commercialPage.waitForSelector(`[data-testid="cal-event-item-${eventId}"]`, { timeout: 15000 });
    await commercialPage.click(`[data-testid="cal-event-item-${eventId}"]`);
    await commercialPage.waitForSelector('[data-testid="event-details-dialog"]', { timeout: 10000 });
    ok("commercial can open event details", true);
    ok("commercial sees description", (await commercialPage.locator('[data-testid="event-details-dialog"]').innerText()).includes("Consignes E2E"));
    ok("commercial has no edit action", (await commercialPage.locator('[data-testid="event-details-edit"]').count()) === 0);
    await commercialContext.close();

    const removed = await adminContext.request.delete(`/api/events/${eventId}`);
    ok("event cleanup", removed.status() === 200, `HTTP ${removed.status()}`);
  } finally {
    await browser.close();
  }
  console.log(`\n${passed} check(s) passed, ${failures.length} failed`);
  if (failures.length) { console.log(`Failed: ${failures.join(", ")}`); process.exit(1); }
  console.log("Event E2E: OK");
})().catch((e) => { console.error("FATAL", e.stack || e); process.exit(2); });
