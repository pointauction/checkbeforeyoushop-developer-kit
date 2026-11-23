import { fileURLToPath } from 'node:url';
import { CbysClient, attributionFor, filterByProgram, formatRate } from '@checkbeforeyoushop/sdk';
import { createFixtureFetch } from '@checkbeforeyoushop/sdk/node';

const args = process.argv.slice(2);
const live = args.includes('--live');
const slug = args.find((arg) => arg !== '--live') ?? 'nike';
const fixtureDir = process.env.CBYS_FIXTURES_DIR ??
  fileURLToPath(new URL('../../../fixtures/live-2026-11-22/', import.meta.url));
const client = new CbysClient({
  fetch: live ? undefined : createFixtureFetch(fixtureDir),
  retries: 0,
  userAgent: 'cbys-developer-kit-sdk-ts/0.1',
});
if (!live) console.log('Recorded snapshot from fixtures.');

const envelope = await client.getStore(slug);
const { merchant, rates } = envelope.data;
const credit = attributionFor(envelope, merchant);
console.log(`\n${merchant.name} | ${credit.page_url}`);
const deltaRows = filterByProgram(rates, 'delta');
if (deltaRows.length === 0) console.log('No tracked Delta SkyMiles listing was returned.');
for (const row of deltaRows) {
  console.log(`${row.portal_name} | ${formatRate(row)} | confirmed ${row.last_confirmed_at}`);
}
console.log(`\n${credit.attribution}\n${credit.disclosure}`);
