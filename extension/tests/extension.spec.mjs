import { chromium, expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const chromeDir = fileURLToPath(new URL('../chrome', import.meta.url));
const fixturesDir = new URL('../../fixtures/live-2026-11-22/', import.meta.url);

async function attachToPopup(browserSession, targetId) {
  // Chromium's toolbar popup starts as an "other" target before its page loads.
  // Attach through CDP because Playwright does not expose it as a Page.
  const { sessionId } = await browserSession.send('Target.attachToTarget', { targetId });
  let nextId = 0;
  const pending = new Map();
  const events = new Map();
  browserSession.on('Target.receivedMessageFromTarget', (event) => {
    if (event.sessionId !== sessionId) return;
    const message = JSON.parse(event.message);
    if (message.method) {
      events.get(message.method)?.(message.params);
      return;
    }
    const call = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) call?.reject(new Error(message.error.message));
    else call?.resolve(message.result);
  });

  async function send(method, params) {
    const id = ++nextId;
    const result = new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
    await browserSession.send('Target.sendMessageToTarget', {
      sessionId,
      message: JSON.stringify({ id, method, params }),
    });
    return result;
  }

  return {
    send,
    on(event, handler) { events.set(event, handler); },
    async evaluate(expression) {
      const response = await send('Runtime.evaluate', { expression, returnByValue: true });
      if (response.exceptionDetails) throw new Error(response.result.description);
      return response.result.value;
    },
  };
}

test('the unpacked toolbar popup prefills the hostname and looks up fixture rates', async ({}, testInfo) => {
  const profile = testInfo.outputPath('profile');
  const context = await chromium.launchPersistentContext(profile, {
    channel: 'chromium',
    headless: true,
    args: [
      `--disable-extensions-except=${chromeDir}`,
      `--load-extension=${chromeDir}`,
      '--enable-unsafe-extension-debugging',
      '--remote-debugging-port=0',
      '--host-resolver-rules=MAP * ~NOTFOUND',
    ],
  });

  try {
    const manifest = JSON.parse(await readFile(new URL('manifest.json', fixturesDir), 'utf8'));
    const [port, socketPath] = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).trim().split('\n');
    const browser = await chromium.connectOverCDP(`ws://127.0.0.1:${port}${socketPath}`);
    const session = await browser.newBrowserCDPSession();
    const { extensions } = await session.send('Extensions.getExtensions');
    const extension = extensions.find((entry) => entry.path === chromeDir && entry.enabled);
    expect(extension, 'Unpacked extension loaded from the chrome directory').toBeTruthy();

    const shoppingUrl = 'https://squareup.com/products?private=value#fragment';
    await context.route(/^https?:/, (route) => route.request().url().startsWith('https://squareup.com/products?')
      ? route.fulfill({ contentType: 'text/html', body: '<title>Test shopping tab</title>' })
      : route.abort());
    await context.pages()[0].goto(shoppingUrl);
    const { targetInfos: tabs } = await session.send('Target.getTargets', { filter: [{ type: 'tab' }] });
    const tab = tabs.find((entry) => entry.url === shoppingUrl);
    await session.send('Extensions.triggerAction', { id: extension.id, targetId: tab.targetId });

    const popupUrl = `chrome-extension://${extension.id}/popup.html`;
    let popupTarget;
    await expect.poll(async () => {
      const { targetInfos } = await session.send('Target.getTargets');
      popupTarget = targetInfos.find((entry) => entry.url === popupUrl);
      return popupTarget?.targetId;
    }).toBeTruthy();
    const popup = await attachToPopup(session, popupTarget.targetId);
    await expect.poll(() => popup.evaluate('document.querySelector("input")?.value')).toBe('squareup.com');

    const requests = [];
    const routeErrors = [];
    popup.on('Fetch.requestPaused', async ({ requestId, request }) => {
      const url = new URL(request.url);
      requests.push(request.url);
      const query = url.searchParams.get('q');
      // The original fixture set captured store-name searches only. Replay the
      // closest recorded candidates for the synthetic domain and slug queries.
      const fixtureQuery = {
        'squareup.com': 'square',
        'nike.com': 'nike',
        't-mobile-postpaid': 'zzqxnotastore',
      }[query] ?? query;
      const key = query ? url.pathname + '?q=' + fixtureQuery : url.pathname;
      const fixture = manifest.requests[key];
      try {
        if (url.origin !== manifest.base_url || request.method !== 'GET' || !fixture) {
          throw new Error('Unexpected network request ' + request.url);
        }
        const body = await readFile(new URL(fixture.file, fixturesDir));
        await popup.send('Fetch.fulfillRequest', {
          requestId,
          responseCode: fixture.status,
          responseHeaders: [{ name: 'Content-Type', value: 'application/json' }],
          body: body.toString('base64'),
        });
      } catch (error) {
        routeErrors.push(error.message);
        await popup.send('Fetch.failRequest', { requestId, errorReason: 'BlockedByClient' });
      }
    });
    await popup.send('Fetch.enable', { patterns: [{ urlPattern: 'http*' }] });

    await popup.evaluate('document.querySelector("form").requestSubmit()');
    const heading = () => popup.evaluate('document.querySelector(".results h2")?.textContent');
    await expect.poll(heading).toBe('Square');
    await expect(popup.evaluate('Array.from(document.querySelectorAll("h3"), node => node.textContent)')).resolves.toEqual([
      'One-time bonus - cash', 'One-time bonus - miles', 'One-time bonus - points',
    ]);

    async function search(query) {
      await popup.evaluate(`{
        document.querySelector("input").value = ${JSON.stringify(query)};
        document.querySelector("form").requestSubmit();
      }`);
    }

    await search('nike.com');
    await expect.poll(heading).toBe('Choose a store');
    await expect(popup.evaluate('Array.from(document.querySelectorAll(".candidate strong"), node => node.textContent)'))
      .resolves.toEqual(['Nike', 'Nike TW', 'Nike Asia Pacific']);

    await search('t-mobile-postpaid');
    await expect.poll(heading).toBe('T-Mobile Postpaid');
    expect(routeErrors).toEqual([]);
    expect(requests).toEqual([
      'https://checkbeforeyoushop.com/api/v1/search.json?q=squareup.com',
      'https://checkbeforeyoushop.com/api/v1/merchants/square.json',
      'https://checkbeforeyoushop.com/api/v1/search.json?q=nike.com',
      'https://checkbeforeyoushop.com/api/v1/search.json?q=t-mobile-postpaid',
      'https://checkbeforeyoushop.com/api/v1/merchants/t-mobile-postpaid.json',
    ]);
  } finally {
    await context.close();
  }
});
