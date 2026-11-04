#!/usr/bin/env node
/* Cross-browser / responsive smoke test. Missing engines are skipped, not faked. */
const fs = require("fs");
const { chromium, firefox, webkit, devices } = require("playwright");

const BASE = process.env.STAGING_URL || "https://kylot-preview.onrender.com";
const env = Object.fromEntries(fs.readFileSync(process.env.E2E_ENV_FILE || "/tmp/kylot-e2e.env", "utf8")
  .split(/\r?\n/).filter(Boolean).map((line) => { const i = line.indexOf("="); return [line.slice(0, i), line.slice(i + 1)]; }));
let passed = 0; const failures = []; const skipped = [];
function ok(label, cond, detail = "") { if (cond) { passed++; console.log(`PASS ${label}`); } else { failures.push(label); console.log(`FAIL ${label} ${detail}`.trim()); } }

async function runScenario(name, browserType, contextOptions) {
  let browser;
  try { browser = await browserType.launch({ headless: true }); }
  catch (e) { skipped.push(`${name}: ${String(e.message).split("\n")[0]}`); console.log(`SKIP ${name}`); return; }
  const context = await browser.newContext({ baseURL: BASE, ...contextOptions });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  try {
    await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded", timeout: 120000 });
    await page.fill('[data-testid="login-email-input"]', env.E2E_ADMIN_EMAIL);
    await page.fill('[data-testid="login-password-input"]', env.E2E_ADMIN_PASSWORD);
    await page.click('[data-testid="login-submit-btn"]');
    await page.waitForURL(`${BASE}/`, { timeout: 30000 });
    await context.request.post("/api/me/onboarding-complete");
    await page.reload({ waitUntil: "domcontentloaded" });
    ok(`${name} login`, page.url() === `${BASE}/`, page.url());

    for (const [path, needle] of [["/", "Tableau de bord"], ["/clients", "Clients"], ["/ventes", "Ventes"], ["/planning", "Planning"]]) {
      await page.goto(`${BASE}${path}`, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(600);
      const body = await page.locator("body").innerText();
      ok(`${name} ${path} renders`, body.includes(needle), body.slice(0, 200));
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
      ok(`${name} ${path} no horizontal overflow`, !overflow);
    }
    await page.goto(`${BASE}/clients`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(500);
    const a11y = await page.evaluate(() => ({
      imagesWithoutAlt: [...document.images].filter((img) => !img.hasAttribute("alt")).length,
      buttonsWithoutName: [...document.querySelectorAll("button")].filter((b) => !(b.textContent || "").trim() && !b.getAttribute("aria-label")).length,
      unlabeledFields: [...document.querySelectorAll("input, select, textarea")].filter((el) => {
        if (el.type === "hidden") return false;
        if (el.id && document.querySelector(`label[for="${el.id}"]`)) return false;
        if (el.closest("label")) return false;
        return !el.getAttribute("aria-label") && !el.getAttribute("placeholder");
      }).length,
    }));
    ok(`${name} images have alt`, a11y.imagesWithoutAlt === 0, JSON.stringify(a11y));
    ok(`${name} buttons have accessible names`, a11y.buttonsWithoutName === 0, JSON.stringify(a11y));
    ok(`${name} fields have labels or placeholders`, a11y.unlabeledFields === 0, JSON.stringify(a11y));
    ok(`${name} no page exception`, errors.length === 0, errors.join(" | ").slice(0, 400));
  } finally { await browser.close(); }
}

(async () => {
  await runScenario("chromium-desktop", chromium, { viewport: { width: 1440, height: 1000 } });
  await runScenario("chromium-mobile", chromium, { ...devices["iPhone 13"] });
  await runScenario("firefox-desktop", firefox, { viewport: { width: 1440, height: 1000 } });
  await runScenario("webkit-safari", webkit, { viewport: { width: 1440, height: 1000 } });
  if (skipped.length) console.log(`Skipped engines: ${skipped.join(" ; ")}`);
  console.log(`\n${passed} check(s) passed, ${failures.length} failed`);
  if (failures.length) { console.log(`Failed: ${failures.join(", ")}`); process.exit(1); }
  console.log("Browser matrix: OK");
})().catch((e) => { console.error("FATAL", e.stack || e); process.exit(2); });
