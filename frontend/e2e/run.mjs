/* E2E P1 — interface réelle, API mockée, aucun backend requis. */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

const ROOT = path.resolve('build');
const PORT = Number(process.env.E2E_PORT || 4173);
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };

const server = http.createServer((req, res) => {
  const pathname = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
  let file = path.join(ROOT, pathname);
  if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) file = path.join(ROOT, 'index.html');
  res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
});
await new Promise((resolve) => server.listen(PORT, '127.0.0.1', resolve));

const user = {
  id: 'e2e-admin', email: 'e2e@example.invalid', name: 'E2E Admin', role: 'admin',
  company_id: 'e2e-company', permissions: {
    sales: { view: 'all', edit: 'all', delete: 'all' },
    clients: { view: 'all', edit: 'all', delete: 'all' },
    projects: { view: 'all', edit: 'all', delete: 'all' },
    planning: { view: 'all', edit: 'all' },
    stock: { view: 'all', edit: 'all', view_own: true },
    commissions: { view: 'all', edit: 'all' },
    reports: { view: 'all' }, users: { manage: 'all' },
  },
  mfa_setup_required: false, mfa_enabled: true,
};
const project = (id, status, name) => ({ id, status, client_name: name, service: 'Test', city: 'Lille', scheduled_date: '2026-11-20', assigned_to: ['Alice Martin'], priority: 'moyenne', cancelled: false, client_phone: '0600000000' });
const many = (status, n = 12) => Array.from({ length: n }, (_, i) => project(`${status}-${i}`, status, `Client ${i}`));
const sale = (id, name, amount = 1200) => ({ id, client_name: name, amount, status: 'en_cours', sale_date: '2026-11-05', bdc: 'B1', service: 'Test', commercial: 'Alice', payment_method: 'cheque', payment_installments: 1, source: 'R1', commission_rate: 0.1, client_phone: '0600000000', client_city: 'Lille' });

async function mockApi(page) {
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    let body = {};
    if (p === '/api/auth/me') body = user;
    else if (p === '/api/settings') body = { dashboard_widgets: {}, objectif_ca: 100000 };
    else if (p === '/api/team') body = [{ id: 't1', name: 'Alice', type: 'commercial', objectif: 100000 }];
    else if (p === '/api/sale-statuses') body = [{ value: 'en_cours', label: 'En cours', active: true }];
    else if (p === '/api/projects') {
      const status = url.searchParams.get('status') || 'a_planifier';
      const offset = Number(url.searchParams.get('offset') || 0);
      body = status === 'a_planifier' ? (offset === 0 ? many(status, 12) : many(status, 5)) : many(status, 2);
    }
    else if (p === '/api/sales/summary') body = { count: 2, ca_count: 2, total: 2400, by_commercial: [] };
    else if (p === '/api/sales') body = [sale('s1', 'Client Un'), sale('s2', 'Client Deux', 1200)];
    else if (p === '/api/absences' || p === '/api/off-days' || p === '/api/events' || p === '/api/reinterventions') body = [];
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  await page.addInitScript((u) => sessionStorage.setItem('kylot_auth_user', JSON.stringify(u)), user);
}

async function closeOnboarding(page) {
  const skip = page.getByText('Passer et fermer', { exact: false });
  if (await skip.count()) await skip.first().click({ force: true }).catch(() => {});
  await page.waitForTimeout(150);
}

const browser = await chromium.launch();
try {
  const desktop = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const p = await desktop.newPage();
  await mockApi(p);
  await p.goto(`http://127.0.0.1:${PORT}/ventes`, { waitUntil: 'domcontentloaded' });
  await p.waitForTimeout(1000);
  await closeOnboarding(p);
  if (!await p.getByTestId('sales-columns-btn').count()) throw new Error('bouton Colonnes absent');
  const before = await p.locator('.sales-table thead th:visible').allTextContents();
  if (before.includes('Téléphone')) throw new Error('Téléphone devrait être masqué par défaut');
  await p.getByTestId('sales-columns-btn').click();
  await p.getByTestId('sales-column-phone').click();
  await p.waitForTimeout(200);
  const after = await p.locator('.sales-table thead th:visible').allTextContents();
  if (!after.includes('Téléphone')) throw new Error('Téléphone non réaffiché');
  await p.keyboard.press('Escape');
  await p.waitForTimeout(250);
  await p.getByTestId('sale-row-s1').click();
  await p.waitForTimeout(250);
  if (!await p.getByTestId('sale-side-panel').count()) throw new Error('panneau latéral absent');
  await desktop.close();

  const mobile = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const m = await mobile.newPage();
  await mockApi(m);
  await m.goto(`http://127.0.0.1:${PORT}/chantiers`, { waitUntil: 'domcontentloaded' });
  await m.waitForTimeout(1000);
  await closeOnboarding(m);
  if (await m.locator('[data-testid^="kanban-tab-"]').count() !== 3) throw new Error('onglets Kanban absents');
  if (await m.locator('[data-testid="kanban-col-en_cours"]').isVisible()) throw new Error('colonne non sélectionnée visible sur mobile');
  await m.getByTestId('kanban-tab-en_cours').click();
  if (!await m.locator('[data-testid="kanban-col-en_cours"]').isVisible()) throw new Error('onglet En cours ne filtre pas');
  await m.getByTestId('kanban-tab-a_planifier').click();
  await m.getByTestId('kanban-more-a_planifier').click();
  await m.waitForTimeout(250);
  const cards = await m.locator('[data-testid^="kanban-card-a_planifier-"]').count();
  if (cards !== 17) throw new Error(`Charger plus incorrect: ${cards} cartes`);
  if (await m.locator('[data-testid="ai-helper-btn"]').isVisible()) throw new Error('bulle flottante encore visible sur mobile');
  if (!await m.getByTestId('mobile-ai').isVisible()) throw new Error('assistant absent de la nav mobile');
  await mobile.close();
  console.log('E2E P1 OK: colonnes, panneau, onglets, chargement progressif, assistant mobile');
} finally {
  await browser.close();
  server.close();
}
