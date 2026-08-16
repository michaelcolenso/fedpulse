# FedPulse v0.4 — Zero-key source strategy

FedPulse must be able to run its complete baseline nightly pipeline with **zero third-party source API keys**.

## Policy

1. **Required sources must be unauthenticated.** A source is eligible for the baseline only if it can be fetched from an official public endpoint without an account, token, cookie, or API key.
2. **Keyed APIs are optional accelerators only.** They may improve latency, metadata richness, or backfills, but their absence must never degrade baseline health or block publication.
3. **Prefer machine-readable official artifacts over scraping.** XML, JSON, RSS, sitemaps, and bulk repositories outrank HTML parsing.
4. **Keep source clocks separate.** Federal Register, OIRA, Unified Agenda, and GPO/GovInfo freshness are evaluated independently.
5. **Persist provenance.** Every normalized record stores the official source URL, fetch time, source-specific identifier, and raw payload hash where practical.
6. **Fail closed on malformed source data, not on missing optional enrichments.**

## v0.4 baseline sources

### 1. Federal Register API

- Role: canonical daily publication stream.
- Authentication: none.
- Existing FedPulse source; remains the primary publication clock.
- Best joins: Federal Register document number, RIN, docket IDs, agency, dates.

### 2. RegInfo.gov — OIRA EO 12866 XML reports

- Role: pre-publication lifecycle intelligence.
- Authentication: none.
- Machine-readable public XML published by OIRA.
- Daily feeds:
  - rules currently under review
  - reviews completed in the last 30 days
- Strong join key: **RIN**.
- Adds lifecycle states before Federal Register publication:
  - `oira_pending`
  - `oira_completed`
  - `oira_withdrawn` / returned when explicitly represented

### 3. RegInfo.gov — Unified Agenda XML

- Role: planned regulatory lifecycle and long-range intent.
- Authentication: none.
- Machine-readable public XML.
- Strong join key: **RIN**.
- Adds stages such as:
  - `prerule`
  - `proposed_rule`
  - `final_rule`
  - `long_term_action`
  - `completed_action`
- This is a slow-changing planning clock and must not be scored like daily publication activity.

### 4. GovInfo bulk data / RSS / sitemaps

- Role: official bulk corpus and redundancy for selected collections.
- Authentication: none for the public bulk repository, RSS feeds, and sitemaps.
- Prefer bulk XML/JSON endpoints and collection RSS over the keyed GovInfo API.
- Initial v0.4 use: Federal Register bulk cross-check / backfill support and collection discovery.
- Later candidates: eCFR, congressional bill status, statutes, GAO reports, congressionally mandated reports.

## Explicit non-baseline source

### Regulations.gov v4 API

The official v4 API requires an API key. Therefore it is **not a required FedPulse source**.

FedPulse may still:

- link users to public `regulations.gov` docket/document pages when a docket ID is already known from Federal Register data;
- optionally use Regulations.gov API metadata in an enrichment job when a key is available;
- never use that optional enrichment to determine baseline source freshness, pipeline success, or whether a signal exists.

## Lifecycle model

The central v0.4 object should be a **regulatory action keyed primarily by RIN**, not a Regulations.gov docket.

A typical action can progress through:

`agenda_prerule → agenda_proposed → oira_pending → oira_completed → fr_proposed → comments_window → oira_pending_final → oira_completed_final → fr_final → effective`

Not every action follows every step. FedPulse should represent observed evidence, not invent missing stages.

### Join hierarchy

1. RIN (strongest cross-source identifier)
2. Federal Register document number
3. explicit docket ID
4. exact agency + normalized title + bounded date window (weak fallback; diagnostic unless corroborated)

## Product implications

The Today page should eventually say things like:

- “EPA sent a proposed rule to OIRA for review.”
- “OIRA completed review; Federal Register publication is likely the next observable step.”
- “A rule first listed in the Unified Agenda is now under OIRA review.”
- “A final rule was published after 46 days in OIRA review.”

Each statement must link back to the exact official evidence.

## Source-selection checklist

Before adding any new baseline source, answer yes to all:

- official government publisher?
- unauthenticated access?
- stable machine-readable representation?
- deterministic identifier or defensible join?
- documented cadence?
- independently health-checkable?
- useful evidence not already supplied by another source?

If the answer to unauthenticated access is no, the source is optional enrichment only.
