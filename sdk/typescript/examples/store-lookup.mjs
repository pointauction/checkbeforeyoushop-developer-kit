import { fileURLToPath } from 'node:url';
import { CbysClient, CbysNotFoundError, attributionFor, formatRate, groupRatesByUnit } from '@checkbeforeyoushop/sdk';
import { createFixtureFetch } from '@checkbeforeyoushop/sdk/node';

const args = process.argv.slice(2);
const live = args.includes('--live');
const query = args.filter((arg) => arg !== '--live').join(' ') || 'nike';
const fixtureDir = process.env.CBYS_FIXTURES_DIR ??
  fileURLToPath(new URL('../../../fixtures/live-2026-11-22/', import.meta.url));

// Leave at least 1.5 seconds between live GETs when lookup needs multiple requests.
let lastRequestAt = 0;
async function liveFetch(url, init) {
  const delay = lastRequestAt + 1_500 - Date.now();
  if (delay > 0) await new Promise((resolve) => setTimeout(resolve, delay));
  lastRequestAt = Date.now();
  return fetch(url, init);
}

const client = new CbysClient({
  fetch: live ? liveFetch : createFixtureFetch(fixtureDir),
  retries: 0,
  userAgent: 'cbys-developer-kit-sdk-ts/0.1',
});
if (!live) console.log('Recorded snapshot from fixtures.');

async function showStore(store) {
  let envelope;
  try {
    envelope = await client.getStore(store.slug);
  } catch (error) {
    if (!(error instanceof CbysNotFoundError)) throw error;
    console.log(`Search found ${store.name} but its listings are unavailable.`);
    console.log(`${store.slug} | ${store.page_url}`);
    console.log('Search data from CheckBeforeYouShop.com.');
    return;
  }

  const { merchant, rates } = envelope.data;
  const credit = attributionFor(envelope, merchant);
  console.log(`\n${merchant.name} | ${credit.page_url}`);

  for (const [unit, rows] of groupRatesByUnit(rates)) {
    console.log(`\n${unit}`);
    for (const row of rows) {
      const listing = row.listing_label ? ` / ${row.listing_label}` : '';
      console.log(`${row.portal_name}${listing} | ${row.program} | ${formatRate(row)} | confirmed ${row.last_confirmed_at}`);
    }
  }
  console.log(`\n${credit.attribution}\n${credit.disclosure}`);
}

const match = await client.resolveStore(query);
if (match.status === 'found') {
  await showStore(match.store);
} else {
  console.log(match.status === 'ambiguous'
    ? 'Choose a store slug from these matches.'
    : 'No exact store match. Check these suggestions if available.');
  for (const hit of match.status === 'ambiguous' ? match.candidates : match.suggestions) {
    console.log(`${hit.name} | ${hit.slug} | ${hit.page_url}`);
  }
  if (match.portalHits.length) {
    console.log('\nShopping portal matches');
    for (const hit of match.portalHits) console.log(`${hit.name} | ${hit.page_url}`);
  }
  console.log('\nSearch data from CheckBeforeYouShop.com.');
}
