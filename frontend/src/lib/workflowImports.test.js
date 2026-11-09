const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const SYMBOLS = [
  "isSaleCountedInCA",
  "isSalePaid",
  "isSaleCommissionable",
  "salePhase",
  "projectState",
  "canProjectTransition",
  "commissionState",
  "challengeState",
  "canEditChallenge",
  "syncState",
  "canSubmit",
  "canClose",
];

function walk(dir, files = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "__tests__" || entry.name === "node_modules") continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, files);
    else if (/\.(js|jsx)$/.test(entry.name)) files.push(full);
  }
  return files;
}

test("every workflow helper used by a source file is imported", () => {
  const failures = [];
  for (const file of walk(ROOT)) {
    if (file.endsWith("workflows.js") || file.includes(".test.")) continue;
    const source = fs.readFileSync(file, "utf8");
    const used = SYMBOLS.filter((symbol) => new RegExp(`\\b${symbol}\\s*\\(`).test(source));
    if (!used.length) continue;
    const importBlock = source.match(/import\s*\{[^}]*\}\s*from\s*["']@\/lib\/workflows["']/s)?.[0] || "";
    const missing = used.filter((symbol) => !new RegExp(`\\b${symbol}\\b`).test(importBlock));
    if (missing.length) failures.push(`${path.relative(ROOT, file)}: ${missing.join(", ")}`);
  }
  expect(failures).toEqual([]);
});
