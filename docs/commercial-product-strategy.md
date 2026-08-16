# FedPulse commercial product strategy

FedPulse should monetize **decision compression**, not access to public data. The raw inputs are public; the product value is connecting early signals, ranking consequence, and showing exact evidence.

## Highest-value paid signal families

### 1. Federal opportunity radar — strongest near-term product

Sources: Grants.gov forecasts + SAM.gov opportunities + USAspending awards.

Customer: federal contractors, AEC firms, consultants, manufacturers, grant-funded nonprofits, business-development teams.

Paid value:

- opportunities relevant to a company before they become obvious in broad searches
- forecast-to-posted-to-awarded lifecycle
- agency/category spending momentum
- incumbent/recipient and award pattern context
- geography, NAICS and Assistance Listing filters

Why customers pay: this directly affects revenue and pipeline. It is easier to attach ROI to one won opportunity than to general regulatory monitoring.

Suggested product:

**FedPulse Opportunities**

- $49/mo individual — selected markets/agencies, daily brief
- $149/mo professional — saved watch profiles, opportunity/award timelines, CSV exports
- $499+/mo team — multiple profiles, alerts, shared watchlists, API/export

### 2. Regulatory early warning — strongest differentiated intelligence moat

Sources: Unified Agenda + OIRA pending/completed + OIRA meetings + Federal Register.

Customer: regulated companies, trade associations, law firms, compliance teams, government affairs, consultants.

Paid value:

- activity appears before Federal Register publication
- stakeholder pressure visible through OIRA meeting intensity
- RIN-based lifecycle replaces manual cross-site research
- exact evidence/provenance makes the signal defensible

Suggested product:

**FedPulse Regulatory**

- $99/mo professional
- $399–$999/mo team/industry desk depending on coverage and alerts

The key differentiation is not prediction. It is a coherent, source-backed lifecycle with less noise and earlier visibility.

### 3. Federal market movement — strongest executive/strategy product

Sources: Grants.gov + SAM.gov + USAspending, aggregated by agency, NAICS, geography, recipient and program.

Customer: corporate strategy, PE/VC, market researchers, suppliers, economic-development groups.

Paid value:

- where government demand is forming
- where obligations are actually increasing
- which sectors/agencies/geographies are accelerating
- conversion from forecast/opportunity to award

Suggested product:

**FedPulse Markets** at $199–$999/mo depending on team size and export depth.

### 4. Policy-to-market timeline — highest long-term moat

Sources: Congressional Bill Status → Unified Agenda → OIRA → Federal Register → grants/procurement → awards.

Customer: institutional research, consulting, government affairs, investors.

This is the most differentiated product, but it requires more explicit cross-domain citation edges before it should be sold as a finished capability.

## What not to sell

Do not lead with:

- generic Federal Register search
- raw government data downloads
- “AI summaries of regulations”
- black-box predictions
- broad news monitoring

Those are crowded and weakly defensible.

## Best initial commercial wedge

Start with **Federal Opportunity Radar** because the customer can quantify the payoff.

A useful landing-page promise:

> See what the federal government is preparing to fund and buy, what just opened, and where the money actually went — without searching Grants.gov, SAM.gov and USAspending separately.

Then use Regulatory as the differentiation layer:

> See policy activity upstream of future spending and compliance changes.

## Signal scoring for paid products

Keep scoring deterministic and product-specific.

Opportunity priority can combine:

- forecast/new/open stage
- estimated funding or award ceiling
- customer watch-profile match
- agency relevance
- NAICS/category relevance
- response/close date proximity
- unusual agency opportunity volume

Regulatory priority can combine:

- stage transition
- OIRA review status
- OIRA meeting count/acceleration
- Federal Register publication
- significant-rule metadata
- industry/watch-profile match

Market priority can combine:

- award obligations versus agency/category baseline
- new-award counts
- recipient concentration
- geography shifts
- forecast/opportunity growth preceding awards

## Commercial sequence

1. Ship unified event graph and source ingestion.
2. Add deterministic company/watch profiles stored locally or in the browser; no account required initially.
3. Build an Opportunities Today view.
4. Build opportunity → award timelines where identifiers support defensible linkage.
5. Test paid demand with federal contractors/AEC/consulting users.
6. Add Regulatory industry desks once RIN lifecycle coverage is mature.
7. Only then build broader policy-to-market institutional research products.

## North-star metric

The best product metric is not documents indexed. It is:

**valuable government developments surfaced per user per week that led to an investigation, saved watch item, export, share, bid/no-bid decision, compliance action, or other downstream decision.**
