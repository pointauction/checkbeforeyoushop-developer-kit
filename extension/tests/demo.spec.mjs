import { expect, test } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const demoUrl = new URL('../demo/index.html', import.meta.url).href;

test.beforeEach(async ({ page }) => {
  await page.route(/^https?:/, (route) => route.abort());
});

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
  await page.addInitScript(() => {
    globalThis.__CBYS_DEMO_TEST_TRANSFORM__ = (path, response) => {
      if (path === '/api/v1/merchants/nike.json') {
        const rates = response.body.data.rates;
        const index = rates.findIndex((rate) => rate.portal_id === 'gocashback');
        rates.unshift(...rates.splice(index, 1));
      }
      return response;
    };
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
  await expect(equalRates.locator('.amount')).toHaveText(['6%', '6%', '6%', 'Up to 6%']);
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

test('a higher stale rate sorts after fresh rates and displays its own confirmation', async ({ page }) => {
  await page.addInitScript(() => {
    globalThis.__CBYS_DEMO_TEST_TRANSFORM__ = (path, response) => {
      if (path === '/api/v1/merchants/nike.json') {
        const data = response.body.data;
        // Keep the three highest cash rates so the expanded screenshot stays compact.
        data.rates = data.rates.filter((rate) => rate.rate_unit !== 'pct_cash' || rate.rate_value >= 8.5);
        const row = data.rates.find((rate) => rate.portal_id === 'topcashback');
        Object.assign(row, {
          _synthetic_note: 'Stale-row fixture injected for the demo test only.',
          is_stale: true,
          last_confirmed_at: '2026-11-17T09:15:00Z',
        });
        data.verdict = null;
      }
      return response;
    };
  });
  await page.goto(demoUrl);
  await search(page, 'nike');
  const cash = page.getByRole('region', { name: 'Cash back %' });
  await expect(cash.locator('.amount').filter({ visible: true })).toHaveText(['9%', '8.5%']);
  await cash.getByText('Show 1 more listing', { exact: true }).click();
  const stale = cash.locator('.rate').filter({
    has: page.getByRole('link', { name: 'TopCashback', exact: true }),
  });
  await expect(stale.locator('.amount')).toHaveText('10%');
  await expect(stale.getByText('Stale', { exact: true })).toBeVisible();
  await expect(stale.locator('time')).toHaveText('Nov 17, 2026, 9:15 AM UTC');
  await expect(stale.locator('time')).toHaveAttribute('datetime', '2026-11-17T09:15:00Z');
  await screenshot(page, 'stale');
});

test('every verdict caveat appears directly under the headline as text', async ({ page }) => {
  const caveats = [
    'TopCashback rates can vary by item category.',
    'Check whether your coupon code is eligible.',
  ];
  await page.addInitScript((caveats) => {
    globalThis.__CBYS_DEMO_TEST_TRANSFORM__ = (path, response) => {
      if (path === '/api/v1/merchants/nike.json') {
        Object.assign(response.body.data.verdict, {
          _synthetic_note: 'Caveats injected for the demo test only.',
          caveats,
        });
      }
      return response;
    };
  }, caveats);
  await page.goto(demoUrl);
  await search(page, 'nike');
  const verdict = page.locator('.verdict');
  await expect(page.getByText(caveats[0], { exact: true })).toBeVisible();
  await expect(verdict.locator('p')).toHaveText([
    "10% on TopCashback is within Nike's typical range (8–10%).",
    ...caveats,
  ]);
  await screenshot(page, 'caveat');

  await page.evaluate(() => {
    const transform = globalThis.__CBYS_DEMO_TEST_TRANSFORM__;
    globalThis.__CBYS_DEMO_TEST_TRANSFORM__ = (path, response) => {
      const result = transform(path, response);
      if (path === '/api/v1/merchants/nike.json') {
        result.body.data.verdict.caveats.push('<em>Confirm the rate before shopping.</em>');
      }
      return result;
    };
  });
  await search(page, 'nike');
  await expect(verdict.getByText('<em>Confirm the rate before shopping.</em>', { exact: true })).toBeVisible();
  await expect(verdict.locator('em')).toHaveCount(0);
});

test('Macys.com shows the Southwest category rate alongside its advertised ceiling', async ({ page }) => {
  await page.goto(demoUrl);
  await search(page, 'macys');
  await page.getByRole('link', { name: 'Macys.com macys.com', exact: true }).click();
  const points = page.getByRole('region', { name: 'Points per $' });
  await points.getByText(/^Show \d+ more listings$/).click();
  const southwest = points.locator('.rate').filter({
    has: page.getByRole('link', { name: 'Southwest Rapid Rewards Shopping', exact: true }),
  });
  await expect(southwest.locator('.amount')).toHaveText('Up to 4 pts/$');
  await expect(southwest.getByText('Confirmed category · All Other Categories · 3 pts/$', {
    exact: true,
  })).toBeVisible();
});

test('a detail 404 keeps the selected store after a successful search', async ({ page }) => {
  await page.addInitScript(() => {
    globalThis.__CBYS_DEMO_TEST_TRANSFORM__ = (path, response) => {
      if (['/api/v1/merchants/nike.json', '/api/v1/merchants/macys-com.json'].includes(path)) {
        return {
          _synthetic_note: 'Detail lookup with no tracked listings.',
          status: 404,
          body: { error: 'merchant not found' },
        };
      }
      return response;
    };
  });
  await page.goto(demoUrl);
  for (const [query, name, choice] of [
    ['nike', 'Nike'],
    ['macys', 'Macys.com', 'Macys.com macys.com'],
  ]) {
    await search(page, query);
    if (choice) await page.getByRole('link', { name: choice, exact: true }).click();
    await expect.soft(page.getByRole('heading', { name, exact: true })).toBeVisible();
    await expect.soft(page.getByText('No tracked listings returned for this store.')).toBeVisible();
  }
});

function luminance(color) {
  const channels = color.match(/\d+/g).map((channel) => Number(channel) / 255);
  const [red, green, blue] = channels.map((channel) =>
    channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

test('dark mode follows the browser color scheme', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.goto(demoUrl);
  await search(page, 'nike');
  await expect(page.getByRole('region', { name: 'Airline miles per $' })).toBeVisible();
  await expect(page.locator('html')).toHaveCSS('background-color', 'rgb(20, 30, 25)');
  await expect(page.getByRole('searchbox')).toHaveCSS('background-color', 'rgb(28, 42, 34)');
  const colors = await page.getByRole('searchbox').evaluate((input) => {
    const style = getComputedStyle(input);
    return {
      border: style.borderTopColor,
      field: style.backgroundColor,
      page: getComputedStyle(document.documentElement).backgroundColor,
    };
  });
  const border = luminance(colors.border);
  for (const surface of ['field', 'page']) {
    const background = luminance(colors[surface]);
    const ratio = (Math.max(border, background) + 0.05) / (Math.min(border, background) + 0.05);
    expect.soft(ratio, 'Search border contrast against ' + surface).toBeGreaterThanOrEqual(3);
  }
  await screenshot(page, 'nike-dark');
});
