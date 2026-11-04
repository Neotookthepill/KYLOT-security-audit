#!/usr/bin/env node
/* Controlled staging stress test: read-only, no writes. */
const fs = require("fs");
const BASE = process.env.STAGING_URL || "https://kylot-preview.onrender.com";
const env = Object.fromEntries(fs.readFileSync(process.env.E2E_ENV_FILE || "/tmp/kylot-e2e.env", "utf8")
  .split(/\r?\n/).filter(Boolean).map((line) => { const i = line.indexOf("="); return [line.slice(0, i), line.slice(i + 1)]; }));

function pct(values, p) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))];
}
async function login() {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: env.E2E_ADMIN_EMAIL, password: env.E2E_ADMIN_PASSWORD }),
    signal: AbortSignal.timeout(20000),
  });
  if (!res.ok) throw new Error(`login HTTP ${res.status}`);
  const data = await res.json();
  if (data.mfa_required) throw new Error("MFA challenge active on test account");
  const raw = typeof res.headers.getSetCookie === "function" ? res.headers.getSetCookie() : [res.headers.get("set-cookie") || ""];
  const cookie = raw.map((x) => x.split(";")[0]).filter(Boolean).join("; ");
  if (!cookie) throw new Error("no session cookie");
  return cookie;
}
async function run(name, path, total, concurrency, cookie) {
  let next = 0; const latencies = []; let errors = 0; const statuses = {};
  const started = Date.now();
  async function worker() {
    while (true) {
      const i = next++; if (i >= total) return;
      const t = performance.now();
      try {
        const res = await fetch(`${BASE}${path}`, {
          headers: cookie ? { Cookie: cookie } : {},
          signal: AbortSignal.timeout(15000),
        });
        statuses[res.status] = (statuses[res.status] || 0) + 1;
        if (res.status >= 400) errors += 1;
        await res.arrayBuffer();
      } catch (_) { errors += 1; statuses.error = (statuses.error || 0) + 1; }
      latencies.push(performance.now() - t);
    }
  }
  await Promise.all(Array.from({ length: concurrency }, worker));
  const elapsed = Date.now() - started;
  console.log(`${name}: n=${total} c=${concurrency} errors=${errors} total=${elapsed}ms p50=${pct(latencies, 50).toFixed(0)}ms p95=${pct(latencies, 95).toFixed(0)}ms p99=${pct(latencies, 99).toFixed(0)}ms status=${JSON.stringify(statuses)}`);
  return { errors, p95: pct(latencies, 95) };
}

(async () => {
  const cookie = await login();
  // Warm the frontend/backend cold path, then read-only stress.
  await run("warm /health", "/health", 5, 1, null);
  await run("warm /api/clients", "/api/clients?limit=5", 5, 1, cookie);
  const h = await run("stress /health", "/health", 300, 50, null);
  const r = await run("stress /ready", "/ready", 50, 10, null);
  const c = await run("stress /api/clients", "/api/clients?limit=20", 200, 20, cookie);
  const s = await run("stress /api/sales", "/api/sales?limit=20", 100, 10, cookie);
  const ch = await run("stress /api/challenges/current", "/api/challenges/current", 100, 10, cookie);
  const errors = h.errors + r.errors + c.errors + s.errors + ch.errors;
  console.log(`\nControlled stress: ${errors} error(s)`);
  process.exit(errors === 0 ? 0 : 1);
})().catch((e) => { console.error("FATAL", e.stack || e); process.exit(2); });
