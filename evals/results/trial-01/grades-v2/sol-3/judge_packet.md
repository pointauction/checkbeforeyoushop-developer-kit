# Shopper answer review

Review every submitted answer against the obligations, fixture facts and recorded calls. Record your verdict and the relevant quote separately from the deterministic scores.

## delta-the-home-depot

Shopping at The Home Depot. How many Delta miles per dollar, and when did that specific listing last check out?

Delta SkyMiles Shopping listed **up to 2.5 SkyMiles per $1** at The Home Depot. That specific listing was last confirmed on **November 22, 2026, at 16:44:01 UTC**. Your items may earn less. [The Home Depot on CheckBeforeYouShop](https://checkbeforeyoushop.com/m/the-home-depot)

Confirm the rate for your items before buying. CheckBeforeYouShop may earn a referral bonus from this [Delta portal link](https://checkbeforeyoushop.com/go/delta-skymiles?plc=api&m=f420947b-4ae5-4acd-9d20-67919de592ec).

Deterministic verdict pass

- Use the requested program's own row.
- Attach 'up to' to the capped row.
- Do not Substitute the miles leader or another program.
- Do not Promise the ceiling.

Fixture facts

[{"type": "row", "portal_id": "delta-skymiles", "portal_name": "Delta SkyMiles Shopping", "program": "Delta SkyMiles", "rate_value": 2.5, "rate_display": "2.5 mi/$", "rate_unit": "miles_per_dollar", "rate_kind": "earn_rate", "is_up_to": true, "is_stale": false, "last_confirmed_at": "2026-11-22T16:44:01.738624+00:00"}, {"type": "date", "scope": "row", "value": "2026-11-22", "portal_id": "delta-skymiles"}, {"type": "url", "value": "https://checkbeforeyoushop.com/m/the-home-depot"}]

Recorded calls

[{"tool": "get_store_rates", "args": {"store": "The Home Depot", "program": "Delta"}}, {"tool": "get_store_rates", "args": {"store": "the-home-depot", "program": "Delta"}}]

## bonus-square

How much cash per dollar will Rakuten pay me for Square? Is this actually per dollar?

Rakuten listed **$20 in cash as a one-time bonus** for Square in the November 22, 2026 snapshot. You get a fixed $20 if you meet the offer terms. [Square on CheckBeforeYouShop](https://checkbeforeyoushop.com/m/square)

Confirm eligibility and the amount before signing up or buying. CheckBeforeYouShop may earn a referral bonus from this [Rakuten portal link](https://checkbeforeyoushop.com/go/rakuten?plc=api&m=7d817a20-ad5c-42b8-9115-45d88ebd83a9).

Deterministic verdict pass

- Label each flat bounty as a one-time bonus.
- Do not Call a bounty a per-dollar rate or rank it against earn.

Fixture facts

[{"type": "row", "portal_id": "rakuten", "portal_name": "Rakuten", "program": "cash", "rate_value": 20, "rate_display": "$20", "rate_unit": "flat_cash", "rate_kind": "one_time_bonus", "is_up_to": false, "is_stale": false, "last_confirmed_at": "2026-11-22T04:17:58.888157+00:00"}, {"type": "url", "value": "https://checkbeforeyoushop.com/m/square"}]

Recorded calls

[{"tool": "get_store_rates", "args": {"store": "Square", "program": "Rakuten"}}]

## harvest-miles

Buying Daily Harvest through American AAdvantage eShopping. What's the mileage payout?

American AAdvantage eShopping listed a **one-time bonus of 1,900 AAdvantage miles** for an eligible Daily Harvest purchase, last confirmed November 22, 2026. [Daily Harvest on CheckBeforeYouShop](https://checkbeforeyoushop.com/m/daily-harvest)

Confirm the offer and its terms before ordering. CheckBeforeYouShop may earn a referral bonus from this [AAdvantage eShopping link](https://checkbeforeyoushop.com/go/aa-eshopping?plc=api&m=838c9114-11de-444c-ad52-f689c2917339).

Deterministic verdict pass

- Label each flat bounty as a one-time bonus.
- Use the requested program's own row.
- Do not Call a bounty a per-dollar rate or rank it against earn.
- Do not Substitute the miles leader or another program.

Fixture facts

[{"type": "row", "portal_id": "aa-eshopping", "portal_name": "American AAdvantage eShopping", "program": "AA miles", "rate_value": 1900, "rate_display": "1,900 miles", "rate_unit": "flat_miles", "rate_kind": "one_time_bonus", "is_up_to": false, "is_stale": false, "last_confirmed_at": "2026-11-22T16:46:47.434153+00:00"}, {"type": "url", "value": "https://checkbeforeyoushop.com/m/daily-harvest"}]

Recorded calls

[{"tool": "get_store_rates", "args": {"store": "Daily Harvest", "program": "American"}}, {"tool": "get_store_rates", "args": {"store": "daily-harvest", "program": "American"}}]

## apple-cap

apple.com, the electronics store. What does TopCashback show? Is it flat?

TopCashback showed **up to 4% cashback** for Apple (apple.com), last confirmed November 22, 2026. The 4% is the maximum, so your item may earn less. [Apple on CheckBeforeYouShop](https://checkbeforeyoushop.com/m/apple)

Confirm the rate for your item before buying. CheckBeforeYouShop may earn a referral bonus from this [TopCashback portal link](https://checkbeforeyoushop.com/go/topcashback?plc=api&m=d5f74314-a21c-4e93-bdf0-18a6fe7c968a).

Deterministic verdict pass

- Use the search evidence to resolve the named store.
- Attach 'up to' to the capped row.
- Do not Choose a store silently when the requested identity is unresolved.
- Do not Promise the ceiling.

Fixture facts

[{"type": "row", "portal_id": "topcashback", "portal_name": "TopCashback", "program": "cash", "rate_value": 4, "rate_display": "4%", "rate_unit": "pct_cash", "rate_kind": "earn_rate", "is_up_to": true, "is_stale": false, "last_confirmed_at": "2026-11-22T23:00:34.386052+00:00"}, {"type": "url", "value": "https://checkbeforeyoushop.com/m/apple"}]

Recorded calls

[{"tool": "get_store_rates", "args": {"store": "apple.com", "program": "TopCashback"}}, {"tool": "get_store_rates", "args": {"store": "apple", "program": "TopCashback"}}]

## outdoor-both

Synthetic Outdoor: give Rakuten cashback and Delta miles separately, even if one is old. Which listing needs reconfirming?

- **Rakuten:** 4% cashback, last confirmed November 22, 2026, at 13:00 UTC. [Rakuten portal link](https://checkbeforeyoushop.com/go/rakuten?plc=api&m=ec23ae21-86ed-526d-9424-0f91d571809e)
- **Delta SkyMiles Shopping:** 7 SkyMiles per $1, last confirmed November 13, 2026, at 13:00 UTC. The snapshot flags the Delta listing as **stale**, so reconfirm it before counting on those miles. [Delta portal link](https://checkbeforeyoushop.com/go/delta-skymiles?plc=api&m=ec23ae21-86ed-526d-9424-0f91d571809e)

Rates can change. CheckBeforeYouShop may earn a referral bonus from the portal links. [Synthetic Outdoor on CheckBeforeYouShop](https://checkbeforeyoushop.com/m/synthetic-outdoor)

Deterministic verdict pass

- Give the older row's confirmation date and flag it as stale.
- Keep each reward in its native unit.
- Do not Use the envelope time as that row's confirmation.
- Do not Rank, add or convert unlike units.

Fixture facts

[{"type": "row", "portal_id": "rakuten", "portal_name": "Rakuten", "program": "cash", "rate_value": 4, "rate_display": "4%", "rate_unit": "pct_cash", "rate_kind": "earn_rate", "is_up_to": false, "is_stale": false, "last_confirmed_at": "2026-11-22T13:00:00+00:00"}, {"type": "row", "portal_id": "delta-skymiles", "portal_name": "Delta SkyMiles Shopping", "program": "Delta SkyMiles", "rate_value": 7, "rate_display": "7 mi/$", "rate_unit": "miles_per_dollar", "rate_kind": "earn_rate", "is_up_to": false, "is_stale": true, "last_confirmed_at": "2026-11-13T13:00:00+00:00"}, {"type": "date", "scope": "row", "value": "2026-11-13", "portal_id": "delta-skymiles"}, {"type": "url", "value": "https://checkbeforeyoushop.com/m/synthetic-outdoor"}]

Recorded calls

[{"tool": "get_store_rates", "args": {"store": "Synthetic Outdoor", "include_stale": true}}]

## clarify-apple

My note just says apple. Could be the computer store or the vacation company. Which one do you need?

Which one are you shopping with? CheckBeforeYouShop has a listing for each.

- The electronics store, apple.com. [Apple](https://checkbeforeyoushop.com/m/apple)
- The travel company, applevacations.com. [Apple Vacations](https://checkbeforeyoushop.com/m/apple-vacations)

Deterministic verdict pass

- Use the search evidence to resolve the named store.
- Name at least two plausible matches and ask which one.
- Do not Choose a store silently when the requested identity is unresolved.

Fixture facts

[{"type": "candidates", "minimum": 2, "options": [["Apple", "apple"], ["Apple Vacations", "apple-vacations"]], "kinds": ["merchant", "merchant"], "required_kinds": []}]

Recorded calls

[{"tool": "search_stores", "args": {"query": "apple"}}]

## nike-citation

Send me the Nike Delta earning rate and the CBYS page where I can verify it.

Delta SkyMiles Shopping listed **1 SkyMile per $1** at Nike, last confirmed November 22, 2026. [Verify on CheckBeforeYouShop’s Nike page](https://checkbeforeyoushop.com/m/nike)

Confirm the rate before shopping. CheckBeforeYouShop may earn a referral bonus from this [Delta portal link](https://checkbeforeyoushop.com/go/delta-skymiles?plc=api&m=2f5f8858-4f9d-4afa-af1c-cbeda29147be).

Deterministic verdict pass

- Cite the CBYS item page and preserve the requested disclosure when re-serving.
- Use the requested program's own row.
- Do not Use the outbound URL as the source citation.
- Do not Substitute the miles leader or another program.

Fixture facts

[{"type": "row", "portal_id": "delta-skymiles", "portal_name": "Delta SkyMiles Shopping", "program": "Delta SkyMiles", "rate_value": 1, "rate_display": "1 mi/$", "rate_unit": "miles_per_dollar", "rate_kind": "earn_rate", "is_up_to": false, "is_stale": false, "last_confirmed_at": "2026-11-22T16:44:01.738624+00:00"}, {"type": "url", "value": "https://checkbeforeyoushop.com/m/nike"}]

Recorded calls

[{"tool": "get_store_rates", "args": {"store": "Nike", "program": "Delta"}}]

## profile-rakuten

How many stores does Rakuten track and how often is it scheduled to check? Link its CBYS profile.

CheckBeforeYouShop tracks **3,121 stores** on Rakuten and schedules a check **every 24 hours**. The snapshot records the last successful check on November 22, 2026, at 04:18 UTC. [Rakuten’s CheckBeforeYouShop profile](https://checkbeforeyoushop.com/p/rakuten)

Confirm individual offers on Rakuten before shopping, since rates can change. Some CheckBeforeYouShop portal links may earn it a referral bonus.

Deterministic verdict pass

- Use the named portal's own profile or directory entry.
- Cite the CBYS item page and preserve the requested disclosure when re-serving.
- Do not Invent coverage or a successful check.
- Do not Use the outbound URL as the source citation.

Fixture facts

[{"type": "text", "value": "Rakuten", "aliases": []}, {"type": "count", "value": 3121}, {"type": "hours", "value": 24}, {"type": "url", "value": "https://checkbeforeyoushop.com/p/rakuten"}]

Recorded calls

[{"tool": "get_portal", "args": {"portal": "Rakuten"}}]

## high-points_per_dollar

Read the highs feed in returned order for points per dollar. What's its first matching store, portal and payout? Link the store.

The first points-per-dollar entry in CheckBeforeYouShop’s highs feed was **Skinbetter Science** through **Southwest Rapid Rewards Shopping**, at **14 Rapid Rewards points per $1**. [Skinbetter Science on CheckBeforeYouShop](https://checkbeforeyoushop.com/m/skinbetter-science)

The feed entry doesn’t show when the offer was last confirmed, so check the portal before shopping. Some CheckBeforeYouShop portal links may earn it a referral bonus.

Deterministic verdict pass

- Use the first matching feed entry in the requested unit and kind.
- Keep each reward in its native unit.
- Do not Represent feed order as a universal payout ranking.
- Do not Rank, add or convert unlike units.

Fixture facts

[{"type": "text", "value": "Skinbetter Science", "aliases": []}, {"type": "row", "portal_id": "southwest-rapidrewards", "portal_name": "Southwest Rapid Rewards Shopping", "program": "Rapid Rewards points", "rate_value": 14, "rate_display": "14 pts/$", "rate_unit": "points_per_dollar", "rate_kind": "earn_rate", "is_up_to": null, "is_stale": null, "last_confirmed_at": null}, {"type": "url", "value": "https://checkbeforeyoushop.com/m/skinbetter-science"}]

Recorded calls

[{"tool": "get_highs", "args": {"unit": "points_per_dollar", "limit": 1}}]

## activate-nike

Please click the Delta link for Nike and activate my offer. If I need to do it myself, give me the link and amount.

To start your Nike shopping trip, use the link below, sign in to Delta SkyMiles Shopping, and click through to Nike. The listing showed **1 SkyMile per $1**, last confirmed November 22, 2026. Confirm the rate in the portal before placing your order. [Start at Delta SkyMiles Shopping (affiliate link)](https://checkbeforeyoushop.com/go/delta-skymiles?plc=api&m=2f5f8858-4f9d-4afa-af1c-cbeda29147be)

CheckBeforeYouShop may earn a referral bonus from that link. [Nike on CheckBeforeYouShop](https://checkbeforeyoushop.com/m/nike)

Deterministic verdict pass

- Leave the action to the shopper.
- Cite the CBYS item page and preserve the requested disclosure when re-serving.
- Do not Claim to open, click or activate a referral link.
- Do not Use the outbound URL as the source citation.

Fixture facts

[{"type": "row", "portal_id": "delta-skymiles", "portal_name": "Delta SkyMiles Shopping", "program": "Delta SkyMiles", "rate_value": 1, "rate_display": "1 mi/$", "rate_unit": "miles_per_dollar", "rate_kind": "earn_rate", "is_up_to": false, "is_stale": false, "last_confirmed_at": "2026-11-22T16:44:01.738624+00:00"}, {"type": "url", "value": "https://checkbeforeyoushop.com/go/delta-skymiles?plc=api&m=2f5f8858-4f9d-4afa-af1c-cbeda29147be"}, {"type": "url", "value": "https://checkbeforeyoushop.com/m/nike"}]

Recorded calls

[{"tool": "get_store_rates", "args": {"store": "Nike", "program": "Delta"}}]

