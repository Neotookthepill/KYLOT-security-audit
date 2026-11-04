#!/usr/bin/env node
/* MFA end-to-end checks for the staging admin account.
 * Uses API setup/confirm plus browser login, then disables MFA.
 * Credentials come from /tmp/kylot-e2e.env; secrets are never printed.
 */
const fs = require("fs");
const crypto = require("crypto");
const { chromium } = require("playwright");

const BASE = process.env.STAGING_URL || "https://kylot-preview.onrender.com";
const ENV_FILE = process.env.E2E_ENV_FILE || "/tmp/kylot-e2e.env";
const env = Object.fromEntries(fs.readFileSync(ENV_FILE, "utf8").split(/\r?\n/).filter(Boolean).map((line) => {
  const i = line.indexOf("="); return [line.slice(0, i), line.slice(i + 1)];
}));
const EMAIL = env.E2E_ADMIN_EMAIL;
const PASSWORD = env.E2E_ADMIN_PASSWORD;
const B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

function base32Decode(input) {
  const clean = input.replace(/=+$/, "").toUpperCase().replace(/\s/g, "");
  let bits = 0, value = 0;
  const out = [];
  for (const ch of clean) {
    const idx = B32.indexOf(ch);
    if (idx < 0) throw new Error("Invalid base32 secret");
    value = (value << 5) | idx; bits += 5;
    if (bits >= 8) { out.push((value >>> (bits - 8)) & 0xff); bits -= 8; }
  }
  return Buffer.from(out);
}
function totp(secret, at = Date.now()) {
  const counter = Math.floor(at / 1000 / 30);
  const buf = Buffer.alloc(8); buf.writeBigUInt64BE(BigInt(counter));
  const hmac = crypto.createHmac("sha1", base32Decode(secret)).update(buf).digest();
  const offset = hmac[hmac.length - 1] & 0x0f;
  const code = ((hmac[offset] & 0x7f) << 24 | hmac[offset + 1] << 16 | hmac[offset + 2] << 8 | hmac[offset + 3]) % 1000000;
  return String(code).padStart(6, "0");
}
let passed = 0; const failures = [];
function ok(label, cond, detail = "") { if (cond) { passed++; console.log(`PASS ${label}`); } else { failures.push(label); console.log(`FAIL ${label} ${detail}`.trim()); } }
async function login(context, fillMfa) {
  const page = await context.newPage();
  await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded", timeout: 120000 });
  await page.fill('[data-testid="login-email-input"]', EMAIL);
  await page.fill('[data-testid="login-password-input"]', PASSWORD);
  await page.click('[data-testid="login-submit-btn"]');
  if (fillMfa) {
    await page.waitForSelector('[data-testid="login-mfa-code-input"]', { timeout: 15000 });
    await page.fill('[data-testid="login-mfa-code-input"]', fillMfa);
    await page.click('[data-testid="login-mfa-submit-btn"]');
  }
  await page.waitForURL(`${BASE}/`, { timeout: 30000 });
  return page;
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ baseURL: BASE, viewport: { width: 1440, height: 1000 } });
  const page = await login(context, null);
  const api = context.request;
  let enabled = false;
  let secret = null;
  try {
    const me = await (await api.get("/api/auth/me")).json();
    ok("admin session before MFA", me.email === EMAIL && me.mfa_enabled === false, JSON.stringify({ email: me.email, mfa: me.mfa_enabled }));
    const setup = await api.post("/api/auth/mfa/setup", { data: { password: PASSWORD } });
    const setupBody = await setup.json();
    ok("MFA setup", setup.status() === 200 && setupBody.secret && setupBody.qr_code, `HTTP ${setup.status()}`);
    secret = setupBody.secret;
    const confirm = await api.post("/api/auth/mfa/confirm", { data: { code: totp(secret) } });
    const confirmBody = await confirm.json();
    ok("MFA confirm and recovery codes", confirm.status() === 200 && confirmBody.enabled === true && Array.isArray(confirmBody.recovery_codes) && confirmBody.recovery_codes.length >= 5, `HTTP ${confirm.status()}`);
    enabled = confirm.status() === 200;
    const recovery = confirmBody.recovery_codes?.[0];
    ok("MFA secret not exposed by /auth/me", !JSON.stringify(await (await api.get("/api/auth/me")).json()).includes(secret));

    // Password alone must now return an MFA challenge, not a session.
    await api.post("/api/auth/logout");
    const probeContext = await browser.newContext({ baseURL: BASE });
    const probe = await probeContext.newPage();
    await probe.goto(`${BASE}/login`, { waitUntil: "domcontentloaded" });
    await probe.fill('[data-testid="login-email-input"]', EMAIL);
    await probe.fill('[data-testid="login-password-input"]', PASSWORD);
    await probe.click('[data-testid="login-submit-btn"]');
    await probe.waitForSelector('[data-testid="login-mfa-code-input"]', { timeout: 15000 });
    ok("password alone prompts MFA", true);
    await probeContext.close();

    // Fresh context: password + TOTP.
    const mfaContext = await browser.newContext({ baseURL: BASE });
    await login(mfaContext, totp(secret));
    const now = await (await mfaContext.request.get("/api/auth/me")).json();
    ok("MFA login succeeds", now.email === EMAIL && now.mfa_enabled === true, JSON.stringify({ email: now.email, mfa: now.mfa_enabled }));

    // Recovery code can also complete the challenge.
    await mfaContext.request.post("/api/auth/logout");
    const recoveryContext = await browser.newContext({ baseURL: BASE });
    await login(recoveryContext, recovery);
    const rec = await (await recoveryContext.request.get("/api/auth/me")).json();
    ok("recovery code login succeeds", rec.email === EMAIL, JSON.stringify({ email: rec.email }));

    // Disable with password + current TOTP; then password alone works.
    const disable = await recoveryContext.request.post("/api/auth/mfa/disable", { data: { password: PASSWORD, code: totp(secret) } });
    ok("MFA disable", disable.status() === 200, `HTTP ${disable.status()}`);
    enabled = false;
    await recoveryContext.request.post("/api/auth/logout");
    const afterContext = await browser.newContext({ baseURL: BASE });
    await login(afterContext, null);
    const after = await (await afterContext.request.get("/api/auth/me")).json();
    ok("password login works after disable", after.email === EMAIL && after.mfa_enabled === false);
    await afterContext.close(); await recoveryContext.close(); await mfaContext.close();
  } finally {
    if (enabled && secret) {
      try { await context.request.post("/api/auth/mfa/disable", { data: { password: PASSWORD, code: totp(secret) } }); } catch (_) {}
    }
    await browser.close();
  }
  console.log(`\n${passed} check(s) passed, ${failures.length} failed`);
  if (failures.length) { console.log(`Failed: ${failures.join(", ")}`); process.exit(1); }
  console.log("MFA E2E: OK");
})().catch((e) => { console.error("FATAL", e.stack || e); process.exit(2); });
