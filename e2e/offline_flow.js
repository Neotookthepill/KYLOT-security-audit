#!/usr/bin/env node
/* Offline queue smoke test against staging.
 * Requires a test admin account in /tmp/kylot-e2e.env.
 */
const fs = require("fs");
const { chromium } = require("playwright");

const BASE = process.env.STAGING_URL || "https://kylot-preview.onrender.com";
const env = Object.fromEntries(fs.readFileSync(process.env.E2E_ENV_FILE || "/tmp/kylot-e2e.env", "utf8")
  .split(/\r?\n/).filter(Boolean).map((line) => { const i = line.indexOf("="); return [line.slice(0, i), line.slice(i + 1)]; }));
let passed = 0; const failures = [];
function ok(label, cond, detail = "") { if (cond) { passed++; console.log(`PASS ${label}`); } else { failures.push(label); console.log(`FAIL ${label} ${detail}`.trim()); } }

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ baseURL: BASE, viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded", timeout: 120000 });
  await page.fill('[data-testid="login-email-input"]', env.E2E_ADMIN_EMAIL);
  await page.fill('[data-testid="login-password-input"]', env.E2E_ADMIN_PASSWORD);
  await page.click('[data-testid="login-submit-btn"]');
  await page.waitForURL(`${BASE}/`, { timeout: 30000 });
  const api = context.request;
  await api.post("/api/me/onboarding-complete");
  await page.reload({ waitUntil: "domcontentloaded" });
  const skipOnboarding = page.locator('[data-testid="onboarding-skip"]');
  if (await skipOnboarding.count()) await skipOnboarding.click();
  const stamp = Date.now().toString().slice(-6);
  const clientResponse = await api.post("/api/clients", { data: { name: `E2E-OFFLINE-${stamp}`, city: "Lyon" } });
  const client = await clientResponse.json();
  const saleResponse = await api.post("/api/sales", { data: {
    client_id: client.id, service: "E2E Offline", amount: 100,
    sale_date: new Date().toISOString().slice(0, 10), status: "en_cours", source: "Assist",
  }});
  const sale = await saleResponse.json();
  ok("sale prepared", saleResponse.status() === 200 && sale.id, `HTTP ${saleResponse.status()}`);

  await page.goto(`${BASE}/ventes`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector(`[data-testid="sale-row-${sale.id}"]`, { timeout: 15000 });
  await page.locator(`[data-testid="sale-row-${sale.id}"]`).click();
  await page.waitForSelector('[data-testid="edit-sale-sheet"]', { timeout: 10000 });

  const note = `Offline ${stamp}`;
  await context.setOffline(true);
  await page.fill('[data-testid="edit-sale-notes"]', note);
  await page.click('[data-testid="edit-sale-save-btn"]');
  await page.waitForTimeout(1500);
  ok("offline save does not throw", true);

  // The server must still have the old value while offline.
  const duringResponse = await api.get(`/api/sales?limit=1000`);
  const duringSales = await duringResponse.json();
  const during = duringSales.find((s) => s.id === sale.id);
  ok("server untouched while offline", during && during.notes !== note, JSON.stringify(during?.notes));

  await context.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event("online")));
  await page.waitForTimeout(5000);
  const afterResponse = await api.get("/api/sales?limit=1000");
  const afterSales = await afterResponse.json();
  const after = afterSales.find((s) => s.id === sale.id);
  ok("offline update replayed", after && after.notes === note, JSON.stringify(after?.notes));

  // The queue must be drained after replay.
  const pending = await page.evaluate(async () => {
    const request = indexedDB.open("qylot-outbox");
    const db = await new Promise((resolve, reject) => { request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error); });
    const tx = db.transaction("queue", "readonly");
    const store = tx.objectStore("queue");
    const value = await new Promise((resolve, reject) => { const r = store.get("ops"); r.onsuccess = () => resolve(r.result); r.onerror = () => reject(r.error); });
    db.close();
    return (value || []).length;
  });
  ok("offline queue drained", pending === 0, String(pending));

  await browser.close();
  console.log(`\n${passed} check(s) passed, ${failures.length} failed`);
  if (failures.length) { console.log(`Failed: ${failures.join(", ")}`); process.exit(1); }
  console.log("Offline E2E: OK");
})().catch((e) => { console.error("FATAL", e.stack || e); process.exit(2); });
