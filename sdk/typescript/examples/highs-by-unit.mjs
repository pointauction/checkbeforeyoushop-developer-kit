import { fileURLToPath } from 'node:url';
import { CbysClient, attributionFor, formatRate, groupRatesByUnit } from '@checkbeforeyoushop/sdk';
import { createFixtureFetch } from '@checkbeforeyoushop/sdk/node';

const live = process.argv.includes('--live');
const fixtureDir = process.env.CBYS_FIXTURES_DIR ??
  fileURLToPath(new URL('../../../fixtures/live-2026-11-22/', import.meta.url));
const client = new CbysClient({
  fetch: live ? undefined : createFixtureFetch(fixtureDir),
  retries: 0,
  userAgent: 'cbys-developer-kit-sdk-ts/0.1',
});
if (!live) console.log('Recorded snapshot from fixtures.');

const envelope = await client.getHighs();
console.log(`Newest confirmation in feed | ${envelope.data_as_of ?? 'unavailable'}`);
console.log('The feed omits individual confirmation times and up-to flags. Check the linked store page for details.');

for (const [unit, rows] of groupRatesByUnit(envelope.data.highs)) {
  console.log(`\n${unit} | showing up to three reported values`);
  for (const row of rows.slice(0, 3)) {
    const { page_url } = attributionFor(envelope, row);
    console.log(`${row.merchant_name} | ${row.portal_name} / ${row.program} | ${formatRate(row)} | ${page_url}`);
  }
}
console.log(`\n${envelope.attribution}\n${envelope.disclosure}`);
