#!/usr/bin/env node
/* Phone-number split/call link E2E. */
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
  await context.request.post("/api/me/onboarding-complete");

  const stamp = Date.now().toString().slice(-6);
  const name = `E2E-PHONE-${stamp}`;
  const phone = "0327376451 / 0612569563";
  const created = await context.request.post("/api/clients", { data: { name, phone, city: "Lyon" } });
  ok("client with two phones created", created.status() === 200, `HTTP ${created.status()}`);
  const client = await created.json();

  await page.goto(`${BASE}/clients`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction((n) => document.body.innerText.includes(n), name, { timeout: 15000 }).catch(() => {});
  const row = page.locator(`[data-testid="client-row-${client.id}"]`);
  ok("client row visible", await row.count() === 1);
  const rowLinks = row.locator('a[href^="tel:"]');
  ok("two call links in client row", await rowLinks.count() === 2, String(await rowLinks.count()));
  const hrefs = await rowLinks.evaluateAll((els) => els.map((e) => e.getAttribute("href")));
  ok("first number dialable", hrefs.includes("tel:0327376451"), JSON.stringify(hrefs));
  ok("second number dialable", hrefs.includes("tel:0612569563"), JSON.stringify(hrefs));

  await row.locator("td").first().click();
  await page.waitForSelector('[data-testid="client-detail-dialog"]', { timeout: 10000 });
  const detailLinks = page.locator('[data-testid="client-detail-dialog"] a[href^="tel:"]');
  ok("two call links in client detail", await detailLinks.count() === 2, String(await detailLinks.count()));

  await browser.close();
  console.log(`\n${passed} check(s) passed, ${failures.length} failed`);
  if (failures.length) { console.log(`Failed: ${failures.join(", ")}`); process.exit(1); }
  console.log("Phone E2E: OK");
})().catch((e) => { console.error("FATAL", e.stack || e); process.exit(2); });
