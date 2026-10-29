#!/usr/bin/env node

const fs = require("fs");

const reportPath = process.argv[2];
if (!reportPath) {
  console.error("Usage: node scripts/check-audit.js <yarn-audit.json>");
  process.exit(2);
}

let entries;
try {
  entries = fs
    .readFileSync(reportPath, "utf8")
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
} catch (error) {
  console.error(`Unable to read the Yarn audit report: ${error.message}`);
  process.exit(2);
}

const summary = entries.find((entry) => entry.type === "auditSummary");
if (!summary || !summary.data || !summary.data.vulnerabilities) {
  console.error("Yarn did not produce a usable audit summary.");
  process.exit(2);
}

const vulnerabilities = summary.data.vulnerabilities;
const critical = Number(vulnerabilities.critical || 0);
const high = Number(vulnerabilities.high || 0);
const moderate = Number(vulnerabilities.moderate || 0);
console.log(
  `Dependency advisories: ${critical} critical, ${high} high, ${moderate} moderate.`
);

if (critical > 0) {
  console.error("Critical dependency advisories must be fixed before shipping.");
  process.exit(1);
}

const advisories = entries
  .filter((entry) => entry.type === "auditAdvisory")
  .map((entry) => entry.data && entry.data.advisory)
  .filter(Boolean);
const unexpectedHigh = advisories.filter(
  (advisory) => advisory.severity === "high" && advisory.module_name !== "braces"
);

// CRA 5 currently retains ten duplicate high paths through braces and eight
// moderate paths through sprintf-js. Neither advisory has a patched release.
// Keep this explicit ceiling so new high-severity packages or a larger known
// exposure fail CI instead of blending into the historical build-tool debt.
if (unexpectedHigh.length > 0 || high > 10 || moderate > 8) {
  const modules = [...new Set(unexpectedHigh.map((advisory) => advisory.module_name))];
  console.error(
    `Frontend advisory baseline exceeded${modules.length ? ` by: ${modules.join(", ")}` : ""}.`
  );
  process.exit(1);
}
