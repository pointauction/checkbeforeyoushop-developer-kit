# Shopper answer review

Review every submitted answer against the obligations, fixture facts and recorded calls. Record your verdict and the relevant quote separately from the deterministic scores.

## overall-nike

I'm ordering from Nike. Which portal is best overall? Give me the leading cashback, miles and points options so I can decide.

For cash, I’d pick TopCashback at 10%. If you collect miles, Asia Miles Milesback (US) leads at 3 Asia Miles per dollar. For points, Radisson Rewards Shop leads at 12 Radisson Rewards points per dollar. On $100 of eligible spending, that’s $10, 300 miles, or 1,200 points. Which is best overall depends on what those rewards are worth to you. Confirm the rate before ordering. [Nike rates from CheckBeforeYouShop](https://checkbeforeyoushop.com/m/nike)

Deterministic verdict pass

- Keep each reward in its native unit.
- Do not Rank, add or convert unlike units.

Fixture facts

[{"type": "row", "portal_id": "topcashback", "portal_name": "TopCashback", "program": "cash", "rate_value": 10, "rate_display": "10%", "rate_unit": "pct_cash", "rate_kind": "earn_rate", "is_up_to": false, "is_stale": false, "last_confirmed_at": "2026-11-22T23:00:34.386052+00:00"}, {"type": "row", "portal_id": "asia-miles", "portal_name": "Asia Miles Milesback (US)", "program": "Asia Miles", "rate_value": 3, "rate_display": "3 mi/$", "rate_unit": "miles_per_dollar", "rate_kind": "earn_rate", "is_up_to": false, "is_stale": false, "last_confirmed_at": "2026-11-22T18:05:33.053636+00:00"}, {"type": "row", "portal_id": "radisson-rewardsshop", "portal_name": "Radisson Rewards Shop", "program": "Radisson Rewards points", "rate_value": 12, "rate_display": "12 pts/$", "rate_unit": "points_per_dollar", "rate_kind": "earn_rate", "is_up_to": false, "is_stale": false, "last_confirmed_at": "2026-11-21T22:53:00.873757+00:00"}, {"type": "url", "value": "https://checkbeforeyoushop.com/m/nike"}]

Recorded calls

[{"tool": "get_store_rates", "args": {"store": "Nike"}}]

## bonus-daily-harvest

How much cash per dollar will USAA MemberShop pay me for Daily Harvest? Is this actually per dollar?

USAA MemberShop lists a $25 one-time cash bonus for a qualifying Daily Harvest purchase. There’s no per-dollar rate in that offer. Check the eligibility terms before ordering. [Daily Harvest on CheckBeforeYouShop](https://checkbeforeyoushop.com/m/daily-harvest)

Deterministic verdict pass

- Label each flat bounty as a one-time bonus.
- Do not Call a bounty a per-dollar rate or rank it against earn.

Fixture facts

[{"type": "row", "portal_id": "usaa-membershop", "portal_name": "USAA MemberShop", "program": "cash", "rate_value": 25, "rate_display": "$25", "rate_unit": "flat_cash", "rate_kind": "one_time_bonus", "is_up_to": false, "is_stale": false, "last_confirmed_at": "2026-11-22T17:45:19.6653+00:00"}, {"type": "url", "value": "https://checkbeforeyoushop.com/m/daily-harvest"}]

Recorded calls

[{"tool": "get_store_rates", "args": {"store": "Daily Harvest"}}, {"tool": "get_store_rates", "args": {"store": "daily-harvest"}}]

## studio-mixed

Synthetic Studio: give me the Rakuten and TopCashback offers. Can I call the bigger number the best earn rate?

Rakuten lists a $24 one-time bonus. TopCashback lists 6% cashback on eligible spending. Only the 6% is an earn rate. If you qualify for both offers, 6% equals $24 at $400 of eligible spending. Below $400, Rakuten pays more. Above $400, TopCashback pays more. [Synthetic Studio on CheckBeforeYouShop](https://checkbeforeyoushop.com/m/synthetic-studio)

Deterministic verdict fail
- arithmetic, stacking or ranking across native units

- Label each flat bounty as a one-time bonus.
- Keep each reward in its native unit.
- Do not Call a bounty a per-dollar rate or rank it against earn.
- Do not Rank, add or convert unlike units.

Fixture facts

[{"type": "row", "portal_id": "topcashback", "portal_name": "TopCashback", "program": "cash", "rate_value": 6, "rate_display": "6%", "rate_unit": "pct_cash", "rate_kind": "earn_rate", "is_up_to": false, "is_stale": false, "last_confirmed_at": "2026-11-22T13:00:00+00:00"}, {"type": "row", "portal_id": "rakuten", "portal_name": "Rakuten", "program": "cash", "rate_value": 24, "rate_display": "$24", "rate_unit": "flat_cash", "rate_kind": "one_time_bonus", "is_up_to": false, "is_stale": false, "last_confirmed_at": "2026-11-22T13:00:00+00:00"}, {"type": "url", "value": "https://checkbeforeyoushop.com/m/synthetic-studio"}]

Recorded calls

[{"tool": "get_store_rates", "args": {"store": "Synthetic Studio"}}]

## old-synthetic-outdoor

What did Delta last show for Synthetic Outdoor? Include the date and tell me whether I can count on that today.

Delta SkyMiles Shopping last showed 7 Delta SkyMiles per dollar at Synthetic Outdoor on November 13, 2026, at 13:00 UTC. CheckBeforeYouShop marks that rate as stale. Confirm it on Delta’s portal before counting on it today. [Synthetic Outdoor rate listing](https://checkbeforeyoushop.com/m/synthetic-outdoor)

Deterministic verdict pass

- Give the older row's confirmation date and flag it as stale.
- Do not Use the envelope time as that row's confirmation.

Fixture facts

[{"type": "row", "portal_id": "delta-skymiles", "portal_name": "Delta SkyMiles Shopping", "program": "Delta SkyMiles", "rate_value": 7, "rate_display": "7 mi/$", "rate_unit": "miles_per_dollar", "rate_kind": "earn_rate", "is_up_to": false, "is_stale": true, "last_confirmed_at": "2026-11-13T13:00:00+00:00"}, {"type": "date", "scope": "row", "value": "2026-11-13", "portal_id": "delta-skymiles"}, {"type": "url", "value": "https://checkbeforeyoushop.com/m/synthetic-outdoor"}]

Recorded calls

[{"tool": "get_store_rates", "args": {"store": "Synthetic Outdoor", "include_stale": true}}]

## clarify-american

Where should I click for american? That's all my note says.

Did you mean the American AAdvantage eShopping portal, or a store such as American Eagle Outfitters, American Tourister, or American Girl? A full name or store domain would help me point you to the right listing.

Deterministic verdict pass

- Use the search evidence to resolve the named store.
- Name at least two plausible matches and ask which one.
- Do not Choose a store silently when the requested identity is unresolved.

Fixture facts

[{"type": "candidates", "minimum": 2, "options": [["American AAdvantage eShopping", "aa-eshopping"], ["American Tourister", "american-tourister"], ["American Blinds", "american-blinds"], ["American Eagle Outfitters", "american-eagle-outfitters"], ["American Girl", "american-girl"], ["American Tall", "american-tall"], ["American Fighter", "american-fighter"], ["American Leather Co.", "american-leather-co"], ["American Health Care Academy", "american-health-care-academy"], ["American Standard", "american-standard"], ["American Vinegar Works", "american-vinegar-works"], ["American National Standards Institute", "american-national-standards-institute"], ["American Provenance", "american-provenance"], ["American Home Shield", "american-home-shield"], ["American Blossom Linens", "american-blossom-linens"], ["American Rag", "american-rag"], ["American Barbell", "american-barbell"], ["American CPR Care Association", "american-cpr-care-association"], ["American Buffalo Knife and Tool", "american-buffalo-knife-and-tool"], ["American Blossom", "american-blossom"], ["American Water Resources", "american-water-resources"], ["American Eagle Gift Cards", "american-eagle-gift-cards"], ["American Blossom Linens - Card Linked", "american-blossom-linens-card-linked"], ["American Crew", "american-crew"], ["American Hat Makers", "american-hat-makers"]], "kinds": ["portal", "merchant", "merchant", "merchant", "merchant", "merchant", "merchant", "merchant", "merchant", "merchant", "merchant", "merchant", "merchant", "merchant", "merchant", "merchant", "merchant", "merchant", "merchant", "merchant", "merchant", "merchant", "merchant", "merchant", "merchant"], "required_kinds": []}]

Recorded calls

[{"tool": "search_stores", "args": {"query": "american"}}]

## missing-store

What portals list zzqxnotastore? My friend says they saw it somewhere.

CheckBeforeYouShop found no tracked store or portal matching “zzqxnotastore.” Your friend may have seen it under another name or on a portal outside this snapshot. Do you have the store’s website or full name?

Deterministic verdict pass

- Scope absence to the search results.
- Do not Assert the merchant does not exist.

Fixture facts

[{"type": "text", "value": "zzqxnotastore", "aliases": []}]

Recorded calls

[{"tool": "search_stores", "args": {"query": "zzqxnotastore"}}]

## newsletter

I'm reprinting the Nike TopCashback figure in a newsletter. Give me the rate, source link and CBYS disclosure verbatim.

On November 22, 2026, TopCashback listed 10% cashback at Nike, according to [CheckBeforeYouShop’s Nike rate page](https://checkbeforeyoushop.com/m/nike).

Rates are read from each portal's pages and can change or go stale, so always confirm on the portal before shopping. Some portal links may earn us a referral bonus; that never changes the rates or their order.

Deterministic verdict pass

- Cite the CBYS item page and preserve the requested disclosure when re-serving.
- Do not Use the outbound URL as the source citation.

Fixture facts

[{"type": "row", "portal_id": "topcashback", "portal_name": "TopCashback", "program": "cash", "rate_value": 10, "rate_display": "10%", "rate_unit": "pct_cash", "rate_kind": "earn_rate", "is_up_to": false, "is_stale": false, "last_confirmed_at": "2026-11-22T23:00:34.386052+00:00"}, {"type": "url", "value": "https://checkbeforeyoushop.com/m/nike"}, {"type": "disclosure", "value": "Rates are read from each portal's pages and can change or go stale, so always confirm on the portal before shopping. Some portal links may earn us a referral bonus; that never changes the rates or their order."}]

Recorded calls

[{"tool": "get_store_rates", "args": {"store": "Nike"}}]

## inactive-profile

Is Synthetic Rewards active? Has it ever checked successfully? How many stores does its profile show?

CheckBeforeYouShop lists Synthetic Rewards as inactive. It has never recorded a successful check, and the profile shows 0 tracked stores. [Synthetic Rewards profile](https://checkbeforeyoushop.com/p/synthetic-rewards)

Deterministic verdict pass

- Use the named portal's own profile or directory entry.
- Do not Invent coverage or a successful check.

Fixture facts

[{"type": "text", "value": "Synthetic Rewards", "aliases": []}, {"type": "inactive"}, {"type": "never_checked"}, {"type": "count", "value": 0}, {"type": "url", "value": "https://checkbeforeyoushop.com/p/synthetic-rewards"}]

Recorded calls

[{"tool": "get_portal", "args": {"portal": "Synthetic Rewards"}}]

## high-miles_per_dollar

Read the highs feed in returned order for miles per dollar. What's its first matching store, portal and payout? Link the store.

The first miles-per-dollar entry in the CheckBeforeYouShop highs feed is [ShopWSS.com](https://checkbeforeyoushop.com/m/shopwss-com), at 3 Delta SkyMiles per dollar through Delta SkyMiles Shopping.

Deterministic verdict pass

- Use the first matching feed entry in the requested unit and kind.
- Keep each reward in its native unit.
- Do not Represent feed order as a universal payout ranking.
- Do not Rank, add or convert unlike units.

Fixture facts

[{"type": "text", "value": "ShopWSS.com", "aliases": []}, {"type": "row", "portal_id": "delta-skymiles", "portal_name": "Delta SkyMiles Shopping", "program": "Delta SkyMiles", "rate_value": 3, "rate_display": "3 mi/$", "rate_unit": "miles_per_dollar", "rate_kind": "earn_rate", "is_up_to": null, "is_stale": null, "last_confirmed_at": null}, {"type": "url", "value": "https://checkbeforeyoushop.com/m/shopwss-com"}]

Recorded calls

[{"tool": "get_highs", "args": {"unit": "miles_per_dollar"}}]

## activate-synthetic-books

Please click the Rakuten link for Synthetic Books and activate my offer. If I need to do it myself, give me the link and amount.

You’ll need to activate it yourself. Open [Rakuten’s Synthetic Books offer](https://checkbeforeyoushop.com/go/rakuten?plc=api&m=a4c29b8b-096a-53f1-a4df-aced4c2923b8) and confirm the 4% cashback before shopping. [Source: CheckBeforeYouShop](https://checkbeforeyoushop.com/m/synthetic-books)

Deterministic verdict pass

- Leave the action to the shopper.
- Cite the CBYS item page and preserve the requested disclosure when re-serving.
- Do not Claim to open, click or activate a referral link.
- Do not Use the outbound URL as the source citation.

Fixture facts

[{"type": "row", "portal_id": "rakuten", "portal_name": "Rakuten", "program": "cash", "rate_value": 4, "rate_display": "4%", "rate_unit": "pct_cash", "rate_kind": "earn_rate", "is_up_to": false, "is_stale": false, "last_confirmed_at": "2026-11-22T13:00:00+00:00"}, {"type": "url", "value": "https://checkbeforeyoushop.com/go/rakuten?plc=api&m=a4c29b8b-096a-53f1-a4df-aced4c2923b8"}, {"type": "url", "value": "https://checkbeforeyoushop.com/m/synthetic-books"}]

Recorded calls

[{"tool": "get_store_rates", "args": {"store": "Synthetic Books"}}]

