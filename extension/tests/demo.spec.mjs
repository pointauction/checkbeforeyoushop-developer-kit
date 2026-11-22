import { expect, test } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const demoUrl = new URL('../demo/index.html', import.meta.url).href;

async function search(page, query) {
  const input = page.getByRole('searchbox', { name: 'Store name or website' });
  await input.fill(query);
  await input.press('Enter');
}

async function screenshot(page, name) {
  if (!process.env.CBYS_SCREENSHOTS) return;
  await page.evaluate(() => document.activeElement.blur());
  await page.setViewportSize({ width: 380, height: 415 });
  await page.screenshot({
    path: fileURLToPath(new URL(`../screenshots/popup-${name}.png`, import.meta.url)),
    fullPage: true,
    scale: 'device',
  });
}

test('Nike has three independently sorted units and links without prefetch', async ({ page }) => {
  const network = [];
  await page.route(/^https?:/, (route) => {
    network.push(route.request().url());
    return route.abort();
  });
  await page.goto(demoUrl);
  await search(page, 'Nike');
  await expect(page.getByText('Fixture snapshot from 2026-11-22, not current rates.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Nike', exact: true })).toBeFocused();
  await expect(page.getByRole('heading', { level: 3 })).toHaveText([
    'Cash back %', 'Airline miles per $', 'Points per $',
  ]);
  await expect(page.getByText(/best overall|overall best|best rate/i)).toHaveCount(0);
  await expect(page.getByText("10% on TopCashback is within Nike's typical range (8–10%).")).toBeVisible();
  const cash = page.getByRole('region', { name: 'Cash back %' });
  await expect(cash.locator('.amount').filter({ visible: true })).toHaveText(['10%', '9%']);
  const portal = cash.getByRole('link', { name: 'TopCashback', exact: true });
  await expect(portal).toHaveAttribute('href', /^https:\/\/checkbeforeyoushop\.com\/go\/topcashback\?plc=api&m=/);
  await expect(page.getByRole('link', { name: 'View on CheckBeforeYouShop' })).toHaveAttribute(
    'href', 'https://checkbeforeyoushop.com/m/nike',
  );
  const attribution = page.getByRole('contentinfo');
  await expect(attribution).toContainText('Data from CheckBeforeYouShop');
  await expect(attribution).toContainText('Some portal links may earn us a referral bonus');
  await screenshot(page, 'nike-light');

  await cash.getByText(/^Show \d+ more listings$/).click();
  await expect(cash.getByText('Up to 6%', { exact: true })).toBeVisible();
  const equalRates = cash.locator('.rate').filter({
    has: page.locator('.amount').filter({ hasText: /^(Up to )?6%$/ }),
  });
  await expect(equalRates.last()).toContainText('Up to 6%');
  await expect(cash.getByText('Gift card payout')).toBeVisible();
  await portal.hover();
  expect(network).toEqual([]);
});

test('Square shows only one-time bonus groups', async ({ page }) => {
  await page.goto(demoUrl);
  await search(page, 'square');
  await expect(page.getByRole('heading', { name: 'Square', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { level: 3 })).toHaveText([
    'One-time bonus - cash', 'One-time bonus - miles', 'One-time bonus - points',
  ]);
  await screenshot(page, 'square-bonuses');
});

test('American opens a candidate picker and supports keyboard selection', async ({ page }) => {
  await page.goto(demoUrl);
  await search(page, 'american');
  await expect(page.getByRole('heading', { name: 'Choose a store' })).toBeFocused();
  await expect(page.getByRole('link', { name: /American Tourister/ })).toBeVisible();
  await expect(page.getByRole('link', { name: /American Blinds/ })).toBeVisible();
  await expect(page.getByRole('heading', { level: 3 })).toHaveCount(0);
  await expect(page.getByRole('link', { name: /American AAdvantage eShopping/ })).toHaveCount(0);
  await screenshot(page, 'ambiguous');

  await search(page, 'delta');
  const airLines = page.getByRole('link', { name: /Delta Air Lines/ });
  await airLines.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Delta Air Lines', exact: true })).toBeFocused();
});

test('a single partial match still asks the shopper to choose', async ({ page }) => {
  await page.addInitScript(() => {
    globalThis.__CBYS_DEMO_TEST_TRANSFORM__ = (path, response) => {
      if (path === '/api/v1/search.json?q=delta') {
        response.body.data.results = response.body.data.results.filter(
          (result) => result.slug === 'delta-air-lines',
        );
      }
      return response;
    };
  });
  await page.goto(demoUrl);
  await search(page, '  DeLTa  ');
  await expect(page.getByRole('heading', { name: 'Choose a store' })).toBeVisible();
  await expect(page.locator('.candidates .candidate')).toHaveCount(1);
  await expect(page.getByRole('link', { name: 'Delta Air Lines delta-air-lines' })).toBeVisible();
});

test('an empty fixture response is distinct from a missing fixture', async ({ page }) => {
  await page.goto(demoUrl);
  await search(page, 'zzqxnotastore');
  await expect(page.getByRole('heading', { name: 'No tracked store found' })).toBeVisible();
  await expect(page.getByText('Try another name or website.')).toBeVisible();
  await expect(page.getByRole('heading', { level: 3 })).toHaveCount(0);
  await screenshot(page, 'not-found');
  await search(page, 'uncaptured query');
  await expect(page.getByRole('heading', { name: 'Request not in fixtures' })).toBeVisible();
});

test('a synthetic stale row displays its own last confirmation', async ({ page }) => {
  await page.addInitScript(() => {
    globalThis.__CBYS_DEMO_TEST_TRANSFORM__ = (path, response) => {
      if (path === '/api/v1/merchants/nike.json') {
        const row = response.body.data.rates.find((rate) => rate.portal_id === 'asia-miles');
        Object.assign(row, {
          _synthetic_note: 'Stale-row fixture injected for the demo test only.',
          is_stale: true,
          last_confirmed_at: '2026-11-17T09:15:00Z',
        });
      }
      return response;
    };
  });
  await page.goto(demoUrl);
  await search(page, 'nike');
  const stale = page.locator('.rate').filter({ has: page.getByText('Stale', { exact: true }) });
  await expect(stale).toHaveCount(1);
  await expect(stale.getByText('Asia Miles Milesback (US)', { exact: true })).toBeVisible();
  await expect(stale.locator('time')).toHaveText('Nov 17, 2026, 9:15 AM UTC');
  await expect(stale.locator('time')).toHaveAttribute('datetime', '2026-11-17T09:15:00Z');
  await screenshot(page, 'stale');
});

test('dark mode follows the browser color scheme', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto(demoUrl);
  await search(page, 'nike');
  await expect(page.getByRole('region', { name: 'Airline miles per $' })).toBeVisible();
  await expect(page.locator('html')).toHaveCSS('background-color', 'rgb(20, 30, 25)');
  await expect(page.getByRole('searchbox')).toHaveCSS('background-color', 'rgb(28, 42, 34)');
  await screenshot(page, 'nike-dark');
});
