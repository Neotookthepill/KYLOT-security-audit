#!/usr/bin/env node
/* Client import smoke test (bulk CSV-like paste + duplicate handling). */
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
  await page.goto(`${BASE}/clients`, { waitUntil: "domcontentloaded" });
  const skip = page.locator('[data-testid="onboarding-skip"]');
  if (await skip.count()) await skip.click();

  const stamp = Date.now().toString().slice(-6);
  const firstName = `E2E-IMPORT-A-${stamp}`;
  const secondName = `E2E-IMPORT-B-${stamp}`;
  const text = `${firstName};06000000${stamp.slice(0, 2)};${stamp}a@example.fr;1 rue A;69001;Lyon;Import A\n${secondName};06000000${stamp.slice(2, 4)};${stamp}b@example.fr;2 rue B;69002;Lyon;Import B`;

  await page.click('[data-testid="bulk-import-btn"]');
  await page.waitForSelector('[data-testid="bulk-import-dialog"]');
  await page.fill('[data-testid="bulk-import-textarea"]', text);
  await page.waitForSelector('[data-testid="bulk-preview-row-1"]');
  ok("bulk preview shows two rows", (await page.locator('[data-testid^="bulk-preview-row-"]').count()) === 2);
  await page.click('[data-testid="bulk-import-submit"]');
  await page.waitForTimeout(2000);
  const resultText = await page.locator('[data-testid="bulk-import-dialog"]').innerText();
  ok("bulk import creates two clients", /2 client\(s\) créé\(s\)/.test(resultText), resultText.slice(0, 500));
  await page.click('[data-testid="bulk-import-dialog"] button:has-text("Fermer")').catch(() => {});

  const clients = await (await context.request.get("/api/clients?limit=5000")).json();
  ok("imported clients exist server-side", clients.some((c) => c.name === firstName) && clients.some((c) => c.name === secondName));

  // Re-import the same two rows: duplicates must be reported, not duplicated.
  await page.click('[data-testid="bulk-import-btn"]');
  await page.waitForSelector('[data-testid="bulk-import-dialog"]');
  await page.fill('[data-testid="bulk-import-textarea"]', text);
  await page.click('[data-testid="bulk-import-submit"]');
  await page.waitForTimeout(2000);
  const duplicateText = await page.locator('[data-testid="bulk-import-dialog"]').innerText();
  ok("duplicate import is reported", /déjà présent/.test(duplicateText) || /2.*ignor/.test(duplicateText), duplicateText.slice(0, 700));
  const skipped = await page.locator('[data-testid="bulk-import-skipped"]').count();
  ok("duplicate list visible", skipped === 1, String(skipped));

  await page.keyboard.press("Escape");
  await page.waitForSelector('[data-testid="bulk-import-dialog"]', { state: "detached", timeout: 5000 }).catch(() => {});

  // File upload wizard (separate parser from bulk paste).
  const fileClient = `E2E-FILE-${stamp}`;
  const csv = `Nom;Ville;Email\n${fileClient};Lyon;${stamp}c@example.fr\n`;
  await page.click('[data-testid="file-import-btn"]');
  await page.waitForSelector('[data-testid="import-clients-file-dialog"]');
  await page.setInputFiles('[data-testid="import-file-input"]', {
    name: "clients-e2e.csv", mimeType: "text/csv", buffer: Buffer.from(csv, "utf8"),
  });
  await page.click('[data-testid="import-parse-btn"]');
  await page.waitForSelector('[data-testid="import-next-preview-btn"]', { timeout: 15000 });
  const nextPreview = page.locator('[data-testid="import-next-preview-btn"]');
  if (await nextPreview.isDisabled()) {
    const firstSelect = page.locator('[data-testid="import-map-select-0"]');
    await firstSelect.selectOption("name");
  }
  await nextPreview.click();
  await page.waitForSelector('[data-testid="import-execute-btn"]', { timeout: 10000 });
  await page.click('[data-testid="import-execute-btn"]');
  await page.waitForTimeout(2500);
  const fileResult = await page.locator('[data-testid="import-clients-file-dialog"]').innerText();
  ok("file import creates client", /1 nouveau\(x\) client/.test(fileResult) || /Import terminé/.test(fileResult), fileResult.slice(0, 700));
  const afterFile = await (await context.request.get("/api/clients?limit=5000")).json();
  ok("file-imported client exists server-side", afterFile.some((c) => c.name === fileClient));

  await browser.close();
  console.log(`\n${passed} check(s) passed, ${failures.length} failed`);
  if (failures.length) { console.log(`Failed: ${failures.join(", ")}`); process.exit(1); }
  console.log("Import E2E: OK");
})().catch((e) => { console.error("FATAL", e.stack || e); process.exit(2); });
