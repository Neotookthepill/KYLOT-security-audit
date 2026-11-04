#!/usr/bin/env node
/* Modest staging load smoke test. Not a substitute for a real load test. */
const fs = require("fs");
const { chromium } = require("playwright");

const BASE = process.env.STAGING_URL || "https://kylot-preview.onrender.com";
const env = Object.fromEntries(fs.readFileSync(process.env.E2E_ENV_FILE || "/tmp/kylot-e2e.env", "utf8")
  .split(/\r?\n/).filter(Boolean).map((line) => { const i = line.indexOf("="); return [line.slice(0, i), line.slice(i + 1)]; }));

function pct(values, p) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))];
}
async function measure(label, count, fn) {
  const started = Date.now();
  const latencies = [];
  let errors = 0;
  await Promise.all(Array.from({ length: count }, async (_, i) => {
    const t = performance.now();
    try {
      const r = await fn(i);
      if (!r || r.status() >= 400) errors += 1;
    } catch (_) { errors += 1; }
    latencies.push(performance.now() - t);
  }));
  const total = Date.now() - started;
  console.log(`${label}: n=${count} errors=${errors} total=${total}ms p50=${pct(latencies, 50).toFixed(0)}ms p95=${pct(latencies, 95).toFixed(0)}ms max=${Math.max(...latencies).toFixed(0)}ms`);
  return { errors, p95: pct(latencies, 95) };
}

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

  const api = context.request;
  await api.get("/api/clients?limit=5");
  await api.get("/api/sales?limit=5");
  await api.get("/api/projects?limit=5");

  const health = await measure("GET /health", 30, () => api.get("/health"));
  const ready = await measure("GET /ready (MongoDB)", 10, () => api.get("/ready"));
  const clients = await measure("GET /api/clients?limit=20", 20, () => api.get("/api/clients?limit=20"));
  const sales = await measure("GET /api/sales?limit=20", 20, () => api.get("/api/sales?limit=20"));
  const projects = await measure("GET /api/projects?limit=20", 20, () => api.get("/api/projects?limit=20"));
  const challenge = await measure("GET /api/challenges/current", 10, () => api.get("/api/challenges/current"));

  const pages = [];
  for (const path of ["/", "/clients", "/ventes", "/planning"]) {
    const t = performance.now();
    const r = await page.goto(`${BASE}${path}`, { waitUntil: "domcontentloaded", timeout: 30000 });
    pages.push(`${path}=${Math.round(performance.now() - t)}ms${r && r.status() >= 400 ? ` HTTP${r.status()}` : ""}`);
  }
  console.log("Pages:", pages.join(" "));

  await browser.close();
  const errors = health.errors + ready.errors + clients.errors + sales.errors + projects.errors + challenge.errors;
  console.log(`Load smoke: ${errors === 0 ? "OK" : `${errors} error(s)`}`);
  process.exit(errors === 0 ? 0 : 1);
})().catch((e) => { console.error("FATAL", e.stack || e); process.exit(2); });
