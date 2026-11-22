'use strict';

(() => {
  const origin = 'https://checkbeforeyoushop.com';
  const searchPath = (query) => '/api/v1/search.json?q=' + encodeURIComponent(query);
  const merchantPath = (slug) => '/api/v1/merchants/' + encodeURIComponent(slug) + '.json';
  const noListings = 'No tracked listings returned for this store.';
  const unitLabels = new Map([
    ['earn_rate:pct_cash', 'Cash back %'],
    ['earn_rate:miles_per_dollar', 'Airline miles per $'],
    ['earn_rate:points_per_dollar', 'Points per $'],
    ['one_time_bonus:flat_cash', 'One-time bonus - cash'],
    ['one_time_bonus:flat_miles', 'One-time bonus - miles'],
    ['one_time_bonus:flat_points', 'One-time bonus - points'],
  ]);
  const confirmationFormat = new Intl.DateTimeFormat('en-US', {
    day: 'numeric', month: 'short', year: 'numeric', hour: 'numeric', minute: '2-digit',
    timeZone: 'UTC', timeZoneName: 'short',
  });

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function checkedLink(value, pathPrefix) {
    if (!value) return null;
    try {
      const url = new URL(value);
      return url.origin === origin && url.pathname.startsWith(pathPrefix) ? value : null;
    } catch {
      return null;
    }
  }

  function externalLink(label, value, pathPrefix, className) {
    const href = checkedLink(value, pathPrefix);
    if (!href) return element('span', className, label);
    const link = element('a', className, label);
    link.href = href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    return link;
  }

  function exactMatch(store, query) {
    const normalizeHost = (host) => host.toLowerCase().replace(/^www\./, '').replace(/\.$/, '');
    return store.slug.toLowerCase() === query || store.name.toLowerCase() === query ||
      Boolean(store.domain && normalizeHost(store.domain) === normalizeHost(query));
  }

  function formatCategoryRate(value, unit) {
    const number = value.toFixed(2).replace(/\.0+$|(\.\d*?)0+$/, '$1');
    switch (unit) {
      case 'pct_cash': return number + '%';
      case 'miles_per_dollar': return number + ' mi/$';
      case 'points_per_dollar': return number + (number === '1' ? ' pt/$' : ' pts/$');
      case 'cents_per_gallon': return number + '¢/gal';
      case 'flat_cash': return '$' + number;
      case 'flat_miles': return value.toLocaleString('en-US') + (value === 1 ? ' mile' : ' miles');
      case 'flat_points': return value.toLocaleString('en-US') + (value === 1 ? ' pt' : ' pts');
      default: return number + ' ' + unit;
    }
  }

  function renderRate(rate) {
    const row = element('li', 'rate');
    const portal = externalLink(rate.portal_name, rate.go_url, '/go/', 'portal');
    const payout = rate.payout_kind === 'gift_card' ? 'Gift card payout' : rate.program;
    const details = [payout === 'cash' ? null : payout, rate.listing_label].filter(Boolean);
    const label = element('div', 'rate-label');
    label.append(portal);
    if (details.length) label.append(element('div', 'muted', details.join(' · ')));

    const amount = element('span', 'amount');
    if (rate.is_up_to) amount.append(element('span', 'ceiling', 'Up to '));
    amount.append(rate.rate_display);

    const check = element('div', 'confirmation');
    if (rate.is_stale) check.append(element('strong', 'stale', 'Stale'));
    const date = new Date(rate.last_confirmed_at);
    if (rate.last_confirmed_at && Number.isFinite(date.valueOf())) {
      const time = element('time', '', confirmationFormat.format(date));
      time.dateTime = rate.last_confirmed_at;
      time.title = rate.last_confirmed_at;
      check.append('Last confirmed ', time);
    } else {
      check.append('Confirmation time unavailable');
    }

    row.append(label, amount, check);
    if (rate.is_up_to && rate.best_category_value != null && rate.best_category_label) {
      const categoryRate = formatCategoryRate(rate.best_category_value, rate.rate_unit);
      row.append(element('div', 'confirmation', ['Confirmed category', rate.best_category_label, categoryRate].join(' · ')));
    }
    return row;
  }

  function rateList(rows) {
    const list = element('ul', 'rates');
    for (const row of rows) list.append(renderRate(row));
    return list;
  }

  function renderGroups(rates) {
    const groups = new Map();
    for (const rate of rates) {
      const key = rate.rate_kind + ':' + rate.rate_unit;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(rate);
    }

    const sections = element('div', 'groups');
    for (const key of new Set([...unitLabels.keys(), ...groups.keys()])) {
      const rows = groups.get(key);
      if (!rows) continue;
      const section = element('section', 'group');
      const heading = element('h3', '', unitLabels.get(key) ?? key.replace(':', ' / '));
      heading.id = 'rates-' + sections.childElementCount;
      section.setAttribute('aria-labelledby', heading.id);
      rows.sort((a, b) =>
        Number(Boolean(a.is_stale)) - Number(Boolean(b.is_stale)) ||
        (b.best_category_value ?? b.rate_value) - (a.best_category_value ?? a.rate_value) ||
        Number(a.is_up_to) - Number(b.is_up_to),
      );

      const previewCount = 2;
      section.append(heading, rateList(rows.slice(0, previewCount)));
      if (rows.length > previewCount) {
        const more = element('details', 'more');
        const count = rows.length - previewCount;
        const summary = element('summary');
        summary.append(
          element('span', 'more-closed', 'Show ' + count + (count === 1 ? ' more listing' : ' more listings')),
          element('span', 'more-open', 'Show fewer listings'),
        );
        more.append(summary, rateList(rows.slice(previewCount)));
        section.append(more);
      }
      sections.append(section);
    }
    return sections;
  }

  function mount(root, { request, resolveSlug, snapshot }) {
    const header = element('header', 'header');
    const wordmark = element('p', 'wordmark', 'CheckBeforeYouShop');
    header.append(wordmark, element('h1', '', 'Quick lookup'));

    const form = element('form', 'search');
    const label = element('label', '', 'Store name or website');
    label.htmlFor = 'store';
    const input = element('input');
    input.id = 'store';
    input.type = 'search';
    input.placeholder = 'Nike or nike.com';
    input.required = true;
    input.autocomplete = 'off';
    input.spellcheck = false;
    input.maxLength = 256;
    const submit = element('button', 'search-button', 'Search');
    submit.type = 'submit';
    const controls = element('div', 'search-controls');
    controls.append(input, submit);
    form.append(label, controls);

    const status = element('p', 'visually-hidden');
    status.setAttribute('role', 'status');
    const results = element('div', 'results');
    const footer = element('footer', 'footer');
    footer.setAttribute('role', 'contentinfo');
    footer.hidden = true;
    root.append(header);
    if (snapshot) {
      root.append(element('p', 'snapshot', 'Fixture snapshot from ' + snapshot + ', not current rates.'));
    }
    root.append(form, status, results, footer);

    function show(title, content, focusFrom) {
      const shouldFocus = document.activeElement === focusFrom || document.activeElement === document.body;
      const heading = element('h2', '', title);
      heading.tabIndex = -1;
      results.replaceChildren(heading, ...content);
      if (shouldFocus) heading.focus({ preventScroll: true });
      else status.textContent = title;
    }

    function cite(envelope) {
      footer.hidden = false;
      footer.setAttribute('aria-label', 'Data from ' + envelope.source);
      footer.replaceChildren(
        element('p', '', envelope.attribution),
        element('p', '', envelope.disclosure),
      );
    }

    function showStore(envelope, focusFrom) {
      const { merchant, verdict, rates } = envelope.data;
      const intro = element('div', 'store-intro');
      if (merchant.domain) intro.append(element('p', 'domain', merchant.domain));
      if (verdict?.headline || verdict?.caveats?.length) {
        const card = element('div', 'verdict');
        if (verdict.headline) card.append(element('p', '', verdict.headline));
        for (const caveat of verdict.caveats ?? []) card.append(element('p', '', caveat));
        intro.append(card);
      }
      intro.append(externalLink('View on CheckBeforeYouShop', merchant.page_url, '/m/', 'view-store'));
      const content = rates.length
        ? renderGroups(rates)
        : element('p', 'empty', noListings);
      cite(envelope);
      show(merchant.name, [intro, content], focusFrom);
    }

    let pending;
    let edited = false;
    input.addEventListener('input', () => {
      edited = true;
      input.setCustomValidity('');
      pending?.abort();
      status.textContent = '';
    });

    async function run(focusFrom, action) {
      pending?.abort();
      pending = new AbortController();
      const { signal } = pending;
      status.textContent = 'Looking up store…';
      results.setAttribute('aria-busy', 'true');
      try {
        await action(signal);
      } catch (error) {
        if (signal.aborted) return;
        if (error.code === 'NOT_IN_FIXTURES') {
          show('Request not in fixtures', [element('p', 'empty', 'Try Nike, Square or American.')], focusFrom);
        } else {
          show('Couldn’t load the lookup', [element('p', 'empty', 'Try your search again.')], focusFrom);
        }
      } finally {
        if (signal === pending.signal) {
          results.removeAttribute('aria-busy');
          if (status.textContent === 'Looking up store…') status.textContent = '';
        }
      }
    }

    async function loadStore(store, signal, focusFrom) {
      const response = await request(merchantPath(store.slug), signal);
      if (signal.aborted) return;
      if (response.status === 404) {
        show(store.name, [element('p', 'empty', noListings)], focusFrom);
        return;
      }
      if (response.status !== 200) throw new Error('Merchant lookup failed');
      showStore(response.body, focusFrom);
    }

    function picker(stores) {
      const list = element('ul', 'candidates');
      for (const store of stores) {
        const item = element('li');
        const link = externalLink('', store.page_url, '/m/', 'candidate');
        const choice = link instanceof HTMLAnchorElement ? link : element('button', 'candidate');
        if (choice instanceof HTMLButtonElement) choice.type = 'button';
        choice.append(element('strong', '', store.name), element('span', 'muted', store.domain || store.slug));
        choice.addEventListener('click', (event) => {
          if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
          event.preventDefault();
          run(choice, (signal) => loadStore(store, signal, choice));
        });
        item.append(choice);
        list.append(item);
      }
      return list;
    }

    form.addEventListener('submit', (event) => {
      event.preventDefault();
      const query = input.value.trim().toLowerCase();
      if (query.length < 2) {
        input.setCustomValidity('Enter at least two characters.');
        input.reportValidity();
        return;
      }

      edited = true;
      const focusFrom = document.activeElement;
      footer.hidden = true;
      results.replaceChildren();
      run(focusFrom, async (signal) => {
        const response = await request(searchPath(query), signal);
        if (signal.aborted) return;
        if (response.status !== 200) throw new Error('Search failed');

        const stores = response.body.data.results.filter((entry) => entry.kind === 'merchant');
        const exact = stores.filter((store) => exactMatch(store, query));
        cite(response.body);
        if (exact.length === 1) {
          await loadStore(exact[0], signal, focusFrom);
          return;
        }
        if (exact.length === 0 && resolveSlug) {
          const envelope = await resolveSlug(query, signal);
          if (signal.aborted) return;
          if (envelope) {
            showStore(envelope, focusFrom);
            return;
          }
        }
        const choices = exact.length > 1 ? exact : stores;
        if (choices.length > 0) {
          show('Choose a store', [picker(choices)], focusFrom);
        } else {
          show('No tracked store found', [element('p', 'empty', 'Try another name or website.')], focusFrom);
        }
      });
    });

    return {
      prefill(hostname) {
        if (!edited && !input.value) input.value = hostname;
      },
    };
  }

  globalThis.CbysLookup = { origin, merchantPath, mount };
})();
