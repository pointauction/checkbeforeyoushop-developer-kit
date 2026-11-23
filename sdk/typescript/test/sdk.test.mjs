import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import {
  CbysBadRequestError,
  CbysClient,
  CbysHttpError,
  CbysMixedKindError,
  CbysMixedUnitError,
  CbysNetworkError,
  CbysNotFoundError,
  CbysTimeoutError,
  attributionFor,
  bestPerUnit,
  compareRates,
  filterByProgram,
  formatRate,
  freshness,
  groupRatesByUnit,
} from '@checkbeforeyoushop/sdk';
import { CbysFixtureMissingError, createFixtureFetch } from '@checkbeforeyoushop/sdk/node';

const fixtureDir = fileURLToPath(new URL('../../../fixtures/live-2026-11-22/', import.meta.url));
const fixtureFetch = createFixtureFetch(fixtureDir);
const client = new CbysClient({ fetch: fixtureFetch });
const origin = 'https://checkbeforeyoushop.com';

function envelope(data) {
  return {
    data,
    data_as_of: null,
    source: 'CheckBeforeYouShop',
    attribution: 'Fixture attribution',
    disclosure: 'Fixture disclosure',
  };
}

function jsonResponse(data, init) {
  return new Response(JSON.stringify(data), init);
}

function merchantHit(slug, name, domain, didYouMean = false) {
  return { kind: 'merchant', slug, name, domain, did_you_mean: didYouMean, page_url: `${origin}/m/${slug}` };
}

function searchFixture(...results) {
  return jsonResponse(envelope({ query: '', count: results.length, results, did_you_mean: results.some((row) => row.did_you_mean) }));
}

test('search parses both hit kinds and preserves the envelope', async () => {
  const result = await client.search('  DeLtA  ');
  assert.equal(result.data.query, 'delta');
  assert.equal(result.data.count, result.data.results.length);
  assert.ok(result.data.results.some((hit) => hit.kind === 'merchant'));
  assert.ok(result.data.results.some((hit) => hit.kind === 'portal' && hit.domain === null));
  assert.equal(result.data_as_of, null);
  assert.equal(result.source, 'CheckBeforeYouShop');
  assert.match(result.attribution, /link to each item's page_url/);
  assert.match(result.disclosure, /referral bonus/);
});

test('store parses the verdict and both rate lists, with outbound links as data', async () => {
  const result = await client.getStore('nike');
  const { merchant, verdict, best_rates: bestRates, rates } = result.data;
  assert.equal(merchant.domain, 'nike.com');
  assert.equal(typeof verdict.headline, 'string');
  assert.ok(bestRates.every((row) => Object.hasOwn(row, 'best_category_value') && !Object.hasOwn(row, 'listing_label')));
  assert.ok(rates.every((row) => Object.hasOwn(row, 'listing_label')));
  const goUrl = rates.find((row) => row.go_url)?.go_url;
  assert.equal(new URL(goUrl).searchParams.get('plc'), 'api');
  assert.equal(result.data_as_of, rates.map((row) => row.last_confirmed_at).sort().at(-1));
  assert.deepEqual(attributionFor(result, merchant), {
    source: result.source,
    attribution: result.attribution,
    page_url: merchant.page_url,
    disclosure: result.disclosure,
  });
});

test('portal directory parses active count, payout kind and scrape metadata', async () => {
  const { data } = await client.listPortals();
  assert.equal(data.count, data.portals.length);
  assert.equal(data.active_count, data.portals.filter((portal) => portal.is_active).length);
  const giftCardPortal = data.portals.find((portal) => portal.payout_kind === 'gift_card');
  assert.ok(giftCardPortal);
  assert.equal(typeof giftCardPortal.cadence_hours, 'number');
});

test('portal detail parses merchant links and its own freshness fields', async () => {
  const result = await client.getPortal('delta-skymiles');
  assert.equal(result.data.portal.program, 'Delta SkyMiles');
  assert.equal(result.data.portal.payout_kind, undefined);
  assert.equal(result.data_as_of, result.data.portal.last_success_at);
  const [row] = result.data.top_rates;
  assert.ok(row.page_url.endsWith(`/m/${row.merchant_slug}`));
  assert.equal(typeof row.is_stale, 'boolean');
  assert.equal(freshness(row).ageHours, null);
});

test('highs parse and retain the row-specific fields that are available', async () => {
  const { data } = await client.getHighs();
  assert.equal(data.count, data.highs.length);
  const [row] = data.highs;
  assert.equal(typeof row.is_all_time_high, 'boolean');
  assert.ok(Object.hasOwn(row, 'typical_range'));
  assert.deepEqual(freshness(row), { isStale: null, lastConfirmedAt: null, ageHours: null });
  assert.equal(row.is_up_to, undefined);
  assert.deepEqual(new Set(groupRatesByUnit(data.highs).keys()), new Set(data.highs.map((rate) => rate.rate_unit)));
});

test('transport forwards GET options and keeps extra fields intact', async () => {
  const payload = { ...envelope({ count: 0, highs: [], addedField: 42 }), future: true };
  const mocked = new CbysClient({
    baseUrl: 'https://example.test/prefix/',
    userAgent: 'fixture-test/0.1',
    fetch: async (url, init) => {
      assert.equal(url, 'https://example.test/prefix/api/v1/highs.json');
      assert.equal(init.method, 'GET');
      assert.equal(init.redirect, 'manual');
      assert.equal(init.headers.get('Accept'), 'application/json');
      assert.equal(init.headers.get('User-Agent'), 'fixture-test/0.1');
      return jsonResponse(payload);
    },
  });
  assert.deepEqual(await mocked.getHighs(), payload);
});

test('short queries fail before fetching and HTTP 400 bodies map to CbysBadRequestError', async () => {
  let calls = 0;
  const mocked = new CbysClient({
    fetch: async () => {
      calls++;
      return fixtureFetch(`${origin}/api/v1/search.json?q=a`);
    },
  });
  await assert.rejects(mocked.search(' a '), { name: 'CbysBadRequestError', status: 400 });
  assert.equal(calls, 0);
  await assert.rejects(mocked.search('other'), (error) =>
    error instanceof CbysBadRequestError && error.message === 'q must be at least 2 characters');
  assert.equal(calls, 1);
});

test('store and portal HTTP 404 responses map to CbysNotFoundError', async () => {
  await assert.rejects(client.getStore('does-not-exist-zzq'), (error) =>
    error instanceof CbysNotFoundError && error.status === 404 && error.message === 'merchant not found');
  await assert.rejects(client.getPortal('does-not-exist-zzq'), (error) =>
    error instanceof CbysNotFoundError && error.status === 404 && error.message === 'portal not found');
});

test('fixture env fallback uses manifest keys and missing captures fail on the first attempt', async () => {
  const previous = process.env.CBYS_FIXTURES_DIR;
  process.env.CBYS_FIXTURES_DIR = fixtureDir;
  try {
    const fetch = createFixtureFetch();
    let calls = 0;
    const mocked = new CbysClient({ fetch: (url, init) => {
      calls++;
      return fetch(url, init);
    } });
    assert.equal((await mocked.search(' HOME DEPOT ')).data.query, 'home depot');
    await assert.rejects(mocked.getStore('uncaptured-merchant'), (error) =>
      error instanceof CbysFixtureMissingError && error.key === '/api/v1/merchants/uncaptured-merchant.json');
    assert.equal(calls, 2);
  } finally {
    if (previous === undefined) delete process.env.CBYS_FIXTURES_DIR;
    else process.env.CBYS_FIXTURES_DIR = previous;
  }
});

test('the default retries both a network rejection and a 5xx once before success', async () => {
  const urls = [];
  const mocked = new CbysClient({
    fetch: async (url, init) => {
      assert.equal(init.method, 'GET');
      urls.push(url);
      if (urls.length === 1) throw new TypeError('socket closed');
      if (urls.length === 2) return new Response(null, { status: 503 });
      return jsonResponse(envelope({ count: 0, highs: [] }));
    },
  });
  assert.deepEqual((await mocked.getHighs()).data.highs, []);
  assert.deepEqual(urls, Array(3).fill(`${origin}/api/v1/highs.json`));
});

test('429 respects Retry-After in seconds', async () => {
  let firstAt;
  let elapsed;
  const mocked = new CbysClient({
    retries: 1,
    fetch: async () => {
      if (firstAt === undefined) {
        firstAt = performance.now();
        return new Response(null, { status: 429, headers: { 'Retry-After': '1' } });
      }
      elapsed = performance.now() - firstAt;
      return jsonResponse(envelope({ count: 0, highs: [] }));
    },
  });
  await mocked.getHighs();
  assert.ok(elapsed >= 980, `Retry started after ${elapsed} ms`);
});

test('503 respects an HTTP-date Retry-After', async () => {
  const retryAt = Math.ceil(Date.now() / 1_000) * 1_000 + 1_000;
  let calls = 0;
  const mocked = new CbysClient({
    retries: 1,
    fetch: async () => {
      if (++calls === 1) {
        return new Response(null, { status: 503, headers: { 'Retry-After': new Date(retryAt).toUTCString() } });
      }
      assert.ok(Date.now() >= retryAt - 20);
      return jsonResponse(envelope({ count: 0, highs: [] }));
    },
  });
  await mocked.getHighs();
  assert.equal(calls, 2);
});

test('retry exhaustion throws typed errors and preserves a network cause', async () => {
  let calls = 0;
  const cause = new TypeError('connection refused');
  const offline = new CbysClient({ retries: 1, fetch: async () => { calls++; throw cause; } });
  await assert.rejects(offline.listPortals(), (error) => error instanceof CbysNetworkError && error.cause === cause);
  assert.equal(calls, 2);

  calls = 0;
  const unavailable = new CbysClient({ fetch: async () => {
    calls++;
    return jsonResponse({ error: 'try later' }, { status: 503 });
  } });
  await assert.rejects(unavailable.listPortals(), { name: 'CbysHttpError', status: 503, message: 'try later' });
  assert.equal(calls, 3);
});

test('other HTTP errors and redirects are terminal', async () => {
  for (const status of [302, 403]) {
    let calls = 0;
    const mocked = new CbysClient({ fetch: async (url, init) => {
      calls++;
      assert.equal(url, `${origin}/api/v1/portals.json`);
      assert.equal(init.redirect, 'manual');
      return new Response(null, { status, headers: { Location: `${origin}/go/never-request` } });
    } });
    await assert.rejects(mocked.listPortals(), (error) => error instanceof CbysHttpError && error.status === status);
    assert.equal(calls, 1);
  }
});

test('malformed JSON and malformed envelopes are terminal HTTP errors', async () => {
  for (const [body, message] of [['invalid JSON', /Invalid JSON/], ['{}', /Invalid API response envelope/]]) {
    let calls = 0;
    const mocked = new CbysClient({ fetch: async () => { calls++; return new Response(body); } });
    await assert.rejects(mocked.listPortals(), { name: 'CbysHttpError', status: 200, message });
    assert.equal(calls, 1);
  }
});

test('store detail rejects malformed rates or merchant and accepts an empty rates array', async () => {
  for (const [data, message] of [
    [{ merchant: {} }, /data\.rates/],
    [{ merchant: {}, rates: {} }, /data\.rates/],
    [{ rates: [] }, /data\.merchant/],
  ]) {
    const mocked = new CbysClient({ fetch: async () => jsonResponse(envelope(data)) });
    await assert.rejects(mocked.getStore('nike'), { name: 'CbysHttpError', status: 200, message });
  }
  const mocked = new CbysClient({ fetch: async () => jsonResponse(envelope({ merchant: {}, rates: [] })) });
  assert.deepEqual((await mocked.getStore('nike')).data.rates, []);
});

test('timeout aborts a slow fetch even when it ignores the signal', async () => {
  let calls = 0;
  let signal;
  const mocked = new CbysClient({ timeoutMs: 20, fetch: (_url, init) => {
    calls++;
    signal = init.signal;
    return new Promise(() => {});
  } });
  await assert.rejects(mocked.getHighs(), (error) => error instanceof CbysTimeoutError && error.timeoutMs === 20);
  assert.equal(signal.aborted, true);
  assert.equal(calls, 1);
});

test('timeout includes reading the response body', async () => {
  const mocked = new CbysClient({
    timeoutMs: 20,
    fetch: async () => new Response(new ReadableStream({ start() {} })),
  });
  await assert.rejects(mocked.getHighs(), CbysTimeoutError);
});

test('resolveStore finds exact fixture slugs, including when only merchant detail was captured', async () => {
  for (const slug of ['nike', 'macys-com']) {
    const result = await client.resolveStore(slug.toUpperCase());
    assert.equal(result.status, 'found');
    assert.equal(result.matchedBy, 'slug');
    assert.equal(result.store.slug, slug);
  }
});

test('resolveStore returns merchant candidates and separate portal hits for ambiguous fixtures', async () => {
  for (const q of ['american', 'macys', 'delta']) {
    const result = await client.resolveStore(q);
    assert.equal(result.status, 'ambiguous');
    assert.ok(result.candidates.length > 1);
    assert.ok(result.candidates.every((hit) => hit.kind === 'merchant'));
    assert.ok(result.portalHits.every((hit) => hit.kind === 'portal'));
    if (q === 'delta') assert.ok(result.portalHits.some((hit) => hit.slug === 'delta-skymiles'));
    if (q === 'macys') {
      const slugs = result.candidates.map((hit) => hit.slug);
      assert.ok(slugs.includes('macys-com') && slugs.includes('macy-s-us'));
    }
  }
});

test('resolveStore returns not_found for an empty fixture and passes through suggestions', async () => {
  assert.deepEqual(await client.resolveStore('zzqxnotastore'), { status: 'not_found', suggestions: [], portalHits: [] });
  const suggestion = merchantHit('nike', 'Nike', 'nike.com', true);
  const mocked = new CbysClient({
    fetch: async (url) => url.includes('/search.json')
      ? searchFixture(suggestion)
      : new Response(null, { status: 404 }),
  });
  assert.deepEqual(await mocked.resolveStore('nkie'), { status: 'not_found', suggestions: [suggestion], portalHits: [] });
});

test('resolveStore gives an exact slug precedence when search omits it', async () => {
  const conflictingName = merchantHit('other', 'Nike', 'other.test');
  const mocked = new CbysClient({
    fetch: async (url) => url.includes('/search.json') ? searchFixture(conflictingName) : fixtureFetch(url),
  });
  const found = await mocked.resolveStore('nike');
  assert.equal(found.status, 'found');
  assert.equal(found.matchedBy, 'slug');
  assert.equal(found.store.name, 'Nike');
});

test('resolveStore checks search slugs without case sensitivity', async () => {
  const store = merchantHit('Nike', 'Nike', 'nike.com');
  const urls = [];
  const mocked = new CbysClient({ fetch: async (url) => {
    urls.push(url);
    return searchFixture(store);
  } });
  assert.deepEqual(await mocked.resolveStore(' NIKE '), {
    status: 'found', store, matchedBy: 'slug', portalHits: [],
  });
  assert.equal(urls.length, 1);
  assert.equal(new URL(urls[0]).pathname, '/api/v1/search.json');
});

test('resolveStore leaves fuzzy candidates unresolved if a detail response returns another slug', async () => {
  const candidate = merchantHit('nike', 'Nike', 'nike.com');
  const mocked = new CbysClient({
    fetch: async (url) => url.includes('/search.json')
      ? searchFixture(candidate)
      : fixtureFetch(`${origin}/api/v1/merchants/nike.json`),
  });
  assert.deepEqual(await mocked.resolveStore('nik'), {
    status: 'ambiguous', candidates: [candidate], portalHits: [],
  });
});

test('resolveStore prioritizes exact name over domain and retains exact-domain ties', async () => {
  const byName = merchantHit('example-name', 'Example.com', null);
  const byDomain = merchantHit('example-domain', 'Example', 'example.com');
  const duplicateDomain = merchantHit('example-us', 'Example US', 'example.com');
  const named = new CbysClient({ fetch: async () => searchFixture(byDomain, byName) });
  const domain = new CbysClient({ fetch: async () => searchFixture(byDomain) });
  const tied = new CbysClient({ fetch: async () => searchFixture(byDomain, duplicateDomain) });
  assert.deepEqual(await named.resolveStore(' EXAMPLE.COM '), {
    status: 'found', store: byName, matchedBy: 'name', portalHits: [],
  });
  assert.deepEqual(await domain.resolveStore(' EXAMPLE.COM '), {
    status: 'found', store: byDomain, matchedBy: 'domain', portalHits: [],
  });
  assert.deepEqual(await tied.resolveStore('example.com'), {
    status: 'ambiguous', candidates: [byDomain, duplicateDomain], portalHits: [],
  });
});

test('resolveStore does not select a single fuzzy hit or promote a portal hit', async () => {
  const candidate = merchantHit('home-depot', 'The Home Depot', 'homedepot.com');
  const portal = { ...candidate, kind: 'portal', slug: 'home', domain: null };
  const mocked = new CbysClient({
    fetch: async (url) => url.includes('/search.json')
      ? searchFixture(portal, candidate)
      : new Response(null, { status: 404 }),
  });
  assert.deepEqual(await mocked.resolveStore('home'), {
    status: 'ambiguous', candidates: [candidate], portalHits: [portal],
  });
});

const unitSets = {
  nike: ['pct_cash', 'miles_per_dollar', 'points_per_dollar'],
  square: ['flat_cash', 'flat_miles', 'flat_points'],
  'macys-com': ['pct_cash', 'miles_per_dollar', 'points_per_dollar'],
};

for (const [slug, expectedUnits] of Object.entries(unitSets)) {
  test(`groups and ranks ${slug} by native unit without mutating the input`, async () => {
    const { data: { rates } } = await client.getStore(slug);
    const before = rates.slice();
    const grouped = groupRatesByUnit(rates);
    const best = bestPerUnit(rates);
    assert.deepEqual(new Set(grouped.keys()), new Set(expectedUnits));
    assert.equal(best.size, grouped.size);
    for (const [unit, rows] of grouped) {
      assert.ok(rows.every((row) => row.rate_unit === unit));
      assert.equal(best.get(unit), rows[0]);
      const values = rows.map((row) => row.best_category_value ?? row.rate_value);
      assert.deepEqual(values, [...values].sort((a, b) => b - a));
    }
    assert.deepEqual(rates, before);
    if (slug === 'square') {
      assert.ok(rates.every((row) => row.rate_kind === 'one_time_bonus'));
      assert.ok(rates.every((row) => formatRate(row).includes('one-time bonus')));
    }
  });
}

test('comparison throws before considering values in mixed units or mixed kinds', async () => {
  const { data: { rates } } = await client.getStore('nike');
  const percent = rates.find((row) => row.rate_unit === 'pct_cash');
  const miles = rates.find((row) => row.rate_unit === 'miles_per_dollar');
  assert.throws(() => compareRates(percent, miles), CbysMixedUnitError);
  assert.throws(() => compareRates(percent, { ...percent, rate_kind: 'one_time_bonus' }), CbysMixedKindError);
});

test('same-unit ordering prefers a flat rate to an equal up-to rate and puts stale last', async () => {
  const { data: { rates } } = await client.getStore('nike');
  const rate = rates.find((row) => row.rate_unit === 'pct_cash');
  const flat = { ...rate, rate_value: 8, rate_display: '8%', is_up_to: false, is_stale: false };
  const upTo = { ...flat, is_up_to: true };
  const high = { ...flat, rate_value: 9, rate_display: '9%' };
  const stale = {
    ...flat,
    _synthetic_note: 'Old confirmation with artificially high value tests stale ordering',
    rate_value: 99,
    rate_display: '99%',
    is_stale: true,
    last_confirmed_at: '2026-11-20T00:00:00Z',
  };
  assert.deepEqual(groupRatesByUnit([stale, upTo, high, flat]).get('pct_cash'), [high, flat, upTo, stale]);
  assert.equal(bestPerUnit([stale]).size, 0);
  assert.equal(formatRate(upTo), 'up to 8%');
  assert.equal(formatRate({ ...flat, rate_display: '8' }), '8 (pct_cash)');
  assert.equal(formatRate(stale), '99% [stale]');
  assert.deepEqual(freshness(stale, new Date('2026-11-22T03:00:00Z')), {
    isStale: true, lastConfirmedAt: stale.last_confirmed_at, ageHours: 51,
  });
  assert.equal(freshness({ ...stale, is_stale: false }, new Date('2026-11-22T03:00:00Z')).isStale, false);
  assert.equal(formatRate({ ...flat, rate_unit: 'new_unit', rate_display: '8' }), '8 (new_unit)');
});

test('program filtering finds Delta by program, portal name or id', async () => {
  const { data: { rates, best_rates: bestRates } } = await client.getStore('nike');
  assert.equal(filterByProgram(bestRates, 'delta').length, 0);
  const expected = rates.filter((row) => row.portal_id === 'delta-skymiles');
  assert.ok(expected.length);
  for (const q of [' deLTa ', 'DELTA SKYMILES', 'DELTA SKYMILES SHOPPING', 'DELTA-SKYMILES']) {
    assert.deepEqual(filterByProgram(rates, q), expected);
  }
  assert.deepEqual(filterByProgram(rates, 'unknown-zzq'), []);
});

test('program aliases match the intended portal and never match inside a token', async () => {
  const { data: { rates } } = await client.getStore('nike');
  for (const [query, id] of [
    ['aa', 'aa-eshopping'],
    ['american', 'aa-eshopping'],
    ['aadvantage', 'aa-eshopping'],
    ['delta', 'delta-skymiles'],
    ['united', 'united-mileageplus'],
    ['mileageplus', 'united-mileageplus'],
    ['flying blue', 'flyingblue-shopping'],
  ]) {
    const expected = rates.filter((row) => row.portal_id === id);
    assert.ok(expected.length);
    assert.deepEqual(filterByProgram(rates, query), expected);
  }
  assert.ok(rates.some((row) => row.portal_id === 'usaa-membershop'));
  assert.deepEqual(filterByProgram(rates, 'member'), []);
});

test('generic currency queries tell callers to filter by rate_unit', async () => {
  const { data: { rates } } = await client.getStore('nike');
  for (const query of [' miles ', 'POINTS', 'cash', 'Cashback']) {
    assert.throws(() => filterByProgram(rates, query), {
      name: 'CbysAmbiguousProgramError',
      message: /filter by rate_unit/i,
    });
  }
});

test('exact program, ID, and name matches take precedence over whole-token matches', () => {
  const token = { program: 'Loyalty Gold Rewards', portal_id: 'gold-rewards', portal_name: 'Gold Shopping' };
  const name = { program: 'Other Rewards', portal_id: 'other', portal_name: 'Gold' };
  const id = { program: 'Store Rewards', portal_id: 'gold', portal_name: 'Store' };
  const program = { program: 'Gold', portal_id: 'shop', portal_name: 'Shop' };

  assert.deepEqual(filterByProgram([token, name, id, program], 'gold'), [program]);
  assert.deepEqual(filterByProgram([token, name, id], 'gold'), [id]);
  assert.deepEqual(filterByProgram([token, name], 'gold'), [name]);
  assert.deepEqual(filterByProgram([token], 'gold rewards'), [token]);
});

test('Macys.com shows Delta’s confirmed category and ranks United ahead of it', async () => {
  const { data: { rates } } = await client.getStore('macys-com');
  const [delta] = filterByProgram(rates, 'delta');
  const [united] = filterByProgram(rates, 'united');
  assert.equal(formatRate(delta), 'up to 3.5 mi/$ · All Other Categories: 2.5 mi/$');
  assert.deepEqual(groupRatesByUnit([delta, united]).get('miles_per_dollar'), [united, delta]);
  assert.equal(bestPerUnit([delta, united]).get('miles_per_dollar'), united);

  const plain = { ...united, rate_value: 2.5, is_up_to: false };
  const higherCeiling = { ...delta, rate_value: 4 };
  assert.deepEqual(
    groupRatesByUnit([delta, higherCeiling, plain]).get('miles_per_dollar'),
    [plain, higherCeiling, delta],
  );
  assert.equal(formatRate({ ...delta, best_category_label: null, best_category_value: 0 }),
    'up to 3.5 mi/$ · Confirmed category: 0 mi/$');
});

for (const retries of [0, 1]) {
  test(`terminal 429 exposes the final Retry-After with retries set to ${retries}`, async () => {
    let calls = 0;
    const mocked = new CbysClient({
      retries,
      fetch: async () => jsonResponse({ error: 'slow down' }, {
        status: 429,
        headers: { 'Retry-After': calls++ < retries ? '0' : '12' },
      }),
    });
    await assert.rejects(mocked.getHighs(), (error) =>
      error instanceof CbysHttpError && error.status === 429 &&
      error.message === 'slow down' && error.retryAfterSeconds === 12);
    assert.equal(calls, retries + 1);
  });
}

test('resolveStore uses NFC for both inputs and exact slug, name, and domain matches', async () => {
  const hit = merchantHit('cafe\u0301-shop', 'Cafe\u0301 Shop', 'cafe\u0301.example');
  const mocked = new CbysClient({ fetch: async (url) => {
    const q = new URL(url).searchParams.get('q');
    assert.equal(q, q.normalize('NFC'));
    return searchFixture(hit);
  } });
  for (const [query, matchedBy] of [
    [' CAFE\u0301-SHOP ', 'slug'],
    [' CAFÉ SHOP ', 'name'],
    [' cafe\u0301.example ', 'domain'],
  ]) {
    assert.deepEqual(await mocked.resolveStore(query), { status: 'found', store: hit, matchedBy, portalHits: [] });
  }
});

test('resource lookups normalize slug and portal ID before encoding', async () => {
  const paths = [];
  const mocked = new CbysClient({ fetch: async (url) => {
    paths.push(new URL(url).pathname);
    return jsonResponse(envelope({ merchant: {}, rates: [] }));
  } });
  await mocked.getStore(' cafe\u0301-shop ');
  await mocked.getPortal(' re\u0301wards ');
  await mocked.getPortal('example/plus?region#uk');
  assert.deepEqual(paths, [
    '/api/v1/merchants/caf%C3%A9-shop.json',
    '/api/v1/portals/r%C3%A9wards.json',
    '/api/v1/portals/example%2Fplus%3Fregion%23uk.json',
  ]);
});

test('program matching uses NFC on both sides', () => {
  const row = { program: 'Cafe\u0301 Awards', portal_id: 'orbit', portal_name: 'Orbit Shopping' };
  assert.deepEqual(filterByProgram([row], ' CAFÉ AWARDS '), [row]);
  assert.deepEqual(filterByProgram([{ ...row, program: 'Café Awards' }], 'CAFE\u0301 AWARDS'),
    [{ ...row, program: 'Café Awards' }]);
});

test('store lookup reports a search hit whose listings return 404', async (t) => {
  const dir = await mkdtemp(join(tmpdir(), 'cbys-sdk-test-'));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const requests = {
    '/api/v1/search.json?q=apple': { file: 'search.json', status: 200 },
    '/api/v1/merchants/apple.json': {
      file: 'missing.json', status: 404, _synthetic_note: 'Force a 404 after an exact Apple search hit',
    },
  };
  await Promise.all([
    writeFile(join(dir, 'manifest.json'), JSON.stringify({ requests })),
    writeFile(join(dir, 'search.json'), await readFile(join(fixtureDir, 'search/apple.json'))),
    writeFile(join(dir, 'missing.json'), await readFile(join(fixtureDir, 'merchants/does-not-exist-zzq.json'))),
  ]);
  const output = execFileSync(process.execPath, [
    fileURLToPath(new URL('../examples/store-lookup.mjs', import.meta.url)), 'Apple',
  ], { env: { ...process.env, CBYS_FIXTURES_DIR: dir }, encoding: 'utf8' });
  assert.match(output, /Search found Apple but its listings are unavailable/i);
  assert.match(output, /^apple \| https:\/\/checkbeforeyoushop\.com\/m\/apple$/m);
});

test('formatRate labels a gift card payout, and the store example labels it once', async () => {
  const { data: { rates } } = await client.getStore('nike');
  const [giftCard] = filterByProgram(rates, 'capitalone-shopping');
  assert.equal(formatRate(giftCard), '2% (gift card payout)');
  const output = execFileSync(process.execPath, [
    fileURLToPath(new URL('../examples/store-lookup.mjs', import.meta.url)), 'nike',
  ], { env: { ...process.env, CBYS_FIXTURES_DIR: fixtureDir }, encoding: 'utf8' });
  const line = output.split('\n').find((text) => text.includes('Capital One Shopping'));
  assert.equal(line?.match(/gift card payout/g)?.length, 1);
});

test('the Delta example shows each listing qualifier beside its rate', async (t) => {
  const dir = await mkdtemp(join(tmpdir(), 'cbys-sdk-test-'));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const request = '/api/v1/merchants/nike.json';
  const capture = JSON.parse(await readFile(join(fixtureDir, 'merchants/nike.json'), 'utf8'));
  const [row] = filterByProgram(capture.data.rates, 'delta');
  capture.data.rates = [
    { ...row, rate_value: 5, rate_display: '5 mi/$', listing_label: 'New customers only' },
    { ...row, rate_value: 3, rate_display: '3 mi/$', listing_label: 'Returning customers only' },
    { ...row, rate_value: 2, rate_display: '2 mi/$', listing_label: null },
  ];
  await Promise.all([
    writeFile(join(dir, 'manifest.json'), JSON.stringify({ requests: { [request]: { file: 'nike.json', status: 200 } } })),
    writeFile(join(dir, 'nike.json'), JSON.stringify(capture)),
  ]);
  const output = execFileSync(process.execPath, [
    fileURLToPath(new URL('../examples/delta-check.mjs', import.meta.url)), 'nike',
  ], { env: { ...process.env, CBYS_FIXTURES_DIR: dir }, encoding: 'utf8' });
  const rows = output.split('\n').filter((line) => line.startsWith(row.portal_name));
  assert.deepEqual(rows, [
    `${row.portal_name} / New customers only | 5 mi/$ | confirmed ${row.last_confirmed_at}`,
    `${row.portal_name} / Returning customers only | 3 mi/$ | confirmed ${row.last_confirmed_at}`,
    `${row.portal_name} | 2 mi/$ | confirmed ${row.last_confirmed_at}`,
  ]);
});

test('README and public type declarations give the limits of upstream summary and verdict prose', async () => {
  const [readme, types] = await Promise.all([
    readFile(new URL('../README.md', import.meta.url), 'utf8'),
    readFile(new URL('../dist/types.d.ts', import.meta.url), 'utf8'),
  ]);
  for (const doc of [readme, types]) {
    assert.match(doc, /upstream prose/i);
    assert.match(doc, /across units/i);
    assert.match(doc, /per-unit rows/i);
    assert.match(doc, /preserve .*verdict\.caveats/i);
  }
});

test('SDK includes a copy of the root MIT license in the package manifest', async () => {
  const [root, copy, manifest] = await Promise.all([
    readFile(new URL('../../../LICENSE', import.meta.url), 'utf8'),
    readFile(new URL('../LICENSE', import.meta.url), 'utf8'),
    readFile(new URL('../package.json', import.meta.url), 'utf8'),
  ]);
  assert.match(copy, /MIT License/);
  assert.equal(copy, root);
  assert.ok(JSON.parse(manifest).files.includes('LICENSE'));
});

test('README clone instructions use main and no README references a feat/ branch', async () => {
  const readme = await readFile(new URL('../README.md', import.meta.url), 'utf8');
  assert.match(readme, /^git clone https:\/\/github\.com\/pointauction\/checkbeforeyoushop-developer-kit\.git$/m);
  assert.match(readme, /^cd checkbeforeyoushop-developer-kit\/sdk\/typescript$/m);
  const root = fileURLToPath(new URL('../../../', import.meta.url));
  const tracked = execFileSync('git', ['ls-files', '-z', '--', '*README*.md', '*RUNBOOK*.md'], { cwd: root, encoding: 'utf8' })
    .split('\0')
    .filter(Boolean);
  assert.ok(tracked.includes('README.md'));
  assert.ok(tracked.includes('sdk/typescript/README.md'));
  for (const path of tracked) {
    const text = await readFile(join(root, path), 'utf8');
    assert.doesNotMatch(text, /\bfeat\//, `${path} references a feat/ branch`);
  }
});
