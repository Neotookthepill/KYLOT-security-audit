#!/usr/bin/env node
/* Automated staging checks for KYLOT.
 * Usage: NODE_PATH=/Users/l1l2/node_modules node e2e/staging_flow.js
 * Credentials are read from /tmp/kylot-e2e.env and are never printed.
 */
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE = process.env.STAGING_URL || "https://kylot-preview.onrender.com";
const ENV_FILE = process.env.E2E_ENV_FILE || "/tmp/kylot-e2e.env";
const env = Object.fromEntries(
  fs.readFileSync(ENV_FILE, "utf8").split(/\r?\n/).filter(Boolean).map((line) => {
    const i = line.indexOf("=");
    return [line.slice(0, i), line.slice(i + 1)];
  }),
);
const required = ["E2E_ADMIN_EMAIL", "E2E_ADMIN_PASSWORD", "E2E_COMMERCIAL_EMAIL", "E2E_COMMERCIAL_PASSWORD"];
for (const key of required) if (!env[key]) throw new Error(`Missing ${key} in ${ENV_FILE}`);

let passed = 0;
const failures = [];
function ok(label, condition, detail = "") {
  if (condition) { passed += 1; console.log(`PASS ${label}`); }
  else { failures.push(label); console.log(`FAIL ${label} ${detail}`.trim()); }
}
async function login(context, email, password) {
  const page = await context.newPage();
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded", timeout: 120000 });
  await page.fill('[data-testid="login-email-input"]', email);
  await page.fill('[data-testid="login-password-input"]', password);
  await page.click('[data-testid="login-submit-btn"]');
  await page.waitForURL(`${BASE}/`, { timeout: 30000 });
  return page;
}
async function json(response) { return response.json(); }

(async () => {
  const browser = await chromium.launch({ headless: true });
  const stamp = Date.now().toString().slice(-6);
  const clientName = `E2E-AUTO-${stamp}`;
  const pad = (n) => String(n).padStart(2, "0");
  const now = new Date();
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const monthKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
  const saleDate = iso(now);
  const projectDate = iso(new Date(now.getFullYear(), now.getMonth() + 1, 15));
  const movedProjectDate = iso(new Date(now.getFullYear(), now.getMonth() + 2, 15));
  const projectMonth = projectDate.slice(0, 7);
  const movedProjectMonth = movedProjectDate.slice(0, 7);
  const manualMonth = monthKey(new Date(now.getFullYear(), now.getMonth() + 2, 1));
  const challengeStart = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-01`;
  const challengeEnd = `${now.getFullYear() + (now.getMonth() === 11 ? 1 : 0)}-${pad(((now.getMonth() + 1) % 12) + 1)}-17`;
  const challengeName = `E2E Challenge ${stamp}`;
  let prospecteurId;
  let challengeId;
  let createdChallenge = false;
  let saleId;
  try {
    // 1. Commercial restrictions
    const commercialContext = await browser.newContext({ baseURL: BASE, viewport: { width: 1440, height: 1000 } });
    const commercialPage = await login(commercialContext, env.E2E_COMMERCIAL_EMAIL, env.E2E_COMMERCIAL_PASSWORD);
    ok("commercial login", commercialPage.url() === `${BASE}/`);
    ok("commercial has no Utilisateurs nav", (await commercialPage.getByText("Utilisateurs", { exact: true }).count()) === 0);
    await commercialPage.goto(`${BASE}/utilisateurs`, { waitUntil: "domcontentloaded" });
    await commercialPage.waitForTimeout(800);
    ok("commercial redirected from /utilisateurs", commercialPage.url() === `${BASE}/planning`, commercialPage.url());
    await commercialContext.close();

    // 2. Admin login + UI
    const adminContext = await browser.newContext({ baseURL: BASE, viewport: { width: 1440, height: 1000 } });
    const page = await login(adminContext, env.E2E_ADMIN_EMAIL, env.E2E_ADMIN_PASSWORD);
    const api = adminContext.request;
    ok("admin dashboard", (await page.locator('[data-testid="prospecteur-page"]').count()) === 0 && (await page.title()).includes("QYLOT"));
    const users = await json(await api.get("/api/users"));
    const commercial = users.find((u) => u.email === env.E2E_COMMERCIAL_EMAIL);
    ok("test commercial exists", Boolean(commercial));
    prospecteurId = commercial.id;
    ok("make commercial a prospecteur", (await api.put(`/api/users/${prospecteurId}`, { data: { role: "prospecteur" } })).status() === 200);

    // 3. Client + sale + project
    const clientResponse = await api.post("/api/clients", { data: { name: clientName, phone: "0611111111", city: "Lyon", postal_code: "69000" } });
    const client = await json(clientResponse);
    ok("client created", clientResponse.status() === 200 && client.id, `HTTP ${clientResponse.status()}`);
    const saleResponse = await api.post("/api/sales", { data: {
      client_id: client.id, service: "E2E Chantier", prestations: [{ name: "E2E Chantier", quantity: 1 }],
      amount: 10000, payment_method: "cheque", sale_date: saleDate, source: "Assist",
      commercial: "E2E Admin", status: "commercial_cheque", desired_intervention_date: projectDate,
      prospecteur_id: prospecteurId, prospecteur_commission: 100,
    }});
    const sale = await json(saleResponse);
    saleId = sale.id;
    ok("sale created", saleResponse.status() === 200 && sale.id, `HTTP ${saleResponse.status()}`);
    const projects = await json(await api.get("/api/projects?limit=5000"));
    const project = projects.find((p) => p.sale_id === saleId);
    ok("project created with scheduled date", Boolean(project) && project.scheduled_date === projectDate, JSON.stringify(project?.scheduled_date));

    // 4. Prospection: project month, UI deferred detail
    let rows = await json(await api.get("/api/prospection"));
    let row = rows.find((r) => r.id === saleId);
    ok("prospection derives commission month from project", row?.commission_month === projectMonth && row?.commission_month_source === "project", JSON.stringify(row));
    await page.goto(`${BASE}/prospecteur`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1500);
    const deferredText = await page.locator('[data-testid="prospect-mgr-deferred"]').innerText().catch(() => "");
    ok("manager deferred commission visible", /100/.test(deferredText), deferredText);
    ok("deferred detail shows sale", (await page.locator('[data-testid="prospect-deferred-detail"]').innerText().catch(() => "")).includes(clientName));

    // 5. Project date change updates month
    ok("project date updated", (await api.put(`/api/projects/${project.id}`, { data: { scheduled_date: movedProjectDate } })).status() === 200);
    rows = await json(await api.get("/api/prospection"));
    row = rows.find((r) => r.id === saleId);
    ok("commission month follows project date", row?.commission_month === movedProjectMonth && row?.commission_month_source === "project", JSON.stringify(row));

    // 6. Manual override
    ok("manual month override", (await api.put(`/api/prospection/${saleId}`, { data: { prospect_commission_month: manualMonth } })).status() === 200);
    rows = await json(await api.get("/api/prospection"));
    row = rows.find((r) => r.id === saleId);
    ok("manual override wins", row?.commission_month === manualMonth && row?.commission_month_source === "manual", JSON.stringify(row));
    await page.goto(`${BASE}/prospecteur`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1500);
    ok("far-future deferred detail visible", (await page.locator(`[data-testid="prospect-deferred-month-${saleId}"]`).count()) === 1);

    // 7. Challenge
    const challengeResponse = await api.post("/api/challenges", { data: {
      name: challengeName, start_date: challengeStart, end_date: challengeEnd,
      criterion: "assist", participant_names: ["E2E Admin", "E2E Commercial"],
      rewards: [{ place: 1, amount: 1250 }, { place: 2, amount: 500 }, { place: 3, amount: 250 }],
    }});
    const challenge = await json(challengeResponse);
    challengeId = challenge.id;
    createdChallenge = challengeResponse.status() === 200 && Boolean(challenge.id);
    ok("challenge created", createdChallenge, `HTTP ${challengeResponse.status()}`);
    const current = await json(await api.get("/api/challenges/current"));
    ok("challenge ranking includes E2E Admin", current.challenge?.id === challengeId && current.ranking?.some((r) => r.name === "E2E Admin" && r.count >= 1), JSON.stringify(current).slice(0, 500));
    await page.goto(`${BASE}/`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1500);
    ok("challenge visible on dashboard", (await page.locator("body").innerText()).includes(challengeName));

    // 8. UI smoke on data pages
    await page.goto(`${BASE}/clients`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(800);
    ok("client visible in UI", (await page.locator("body").innerText()).includes(clientName));
    await page.goto(`${BASE}/ventes`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(800);
    ok("sale visible in UI", (await page.locator("body").innerText()).includes("E2E Chantier"));
  } finally {
    // Best-effort cleanup and role restore.
    const adminContexts = browser.contexts().filter((c) => c !== undefined);
    for (const ctx of adminContexts) {
      try {
        const api = ctx.request;
        if (createdChallenge && challengeId) { await api.post(`/api/challenges/${challengeId}/close`); await api.post(`/api/challenges/${challengeId}/archive`); }
        if (prospecteurId) await api.put(`/api/users/${prospecteurId}`, { data: { role: "commercial" } });
      } catch (_) {}
    }
    await browser.close();
  }
  console.log(`\n${passed} check(s) passed, ${failures.length} failed`);
  if (failures.length) { console.log(`Failed: ${failures.join(", ")}`); process.exit(1); }
  console.log("Staging E2E: OK");
})().catch((error) => { console.error("FATAL", error.stack || error); process.exit(2); });
