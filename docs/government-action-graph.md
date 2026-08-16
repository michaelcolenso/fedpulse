# FedPulse government-action graph

FedPulse v0.4 expands from a regulatory-document monitor into a government-action intelligence layer while preserving deterministic evidence and zero required source API keys.

## Core model

The graph has three primitive objects:

### `government_events`

One observed event from one official source. Examples:

- a Unified Agenda action
- an OIRA review
- an EO 12866 stakeholder meeting
- a Federal Register publication
- a Grants.gov forecast/opportunity
- a SAM.gov contract opportunity
- a USAspending award
- a congressional bill update

Events retain source-specific payloads and provenance. They are never merged destructively.

### `government_identifiers`

Typed identifiers attached to events:

- `rin`
- `fr_document`
- `bill`
- `public_law`
- `grants_opportunity`
- `opportunity_number`
- `assistance_listing`
- `sam_notice`
- `solicitation`
- `award`
- `naics`

Identifier namespaces have different semantics. RIN, bill, solicitation and award identifiers can support exact identity/action links. NAICS and Assistance Listing identifiers are classifications/program membership and must not imply identity.

### `government_edges`

Relationships are explicit and carry the method and confidence used to create them. The first implementation creates `same_government_action` edges only from exact shared identifiers.

Future edge types can include:

- `authorized_by` — regulation/program linked to statute
- `funded_by` — award linked to funding opportunity/program
- `procured_from` — award linked to solicitation
- `implements` — agency action implementing legislation
- `responds_to` — company/enforcement event responding to another action
- `same_program` — shared Assistance Listing, explicitly weaker than identity

## Source lifecycle layers

### Policy formation

`bill introduced → committee/floor action → enacted`

Primary source: GovInfo Bill Status bulk XML and RSS.

### Regulatory formation

`Unified Agenda → OIRA review → OIRA meetings → Federal Register proposal/final`

Primary join key: RIN.

### Funding

`Grants.gov forecast → posted opportunity → award`

Primary exact key inside Grants.gov: opportunity ID/number. Assistance Listing provides program-level, not action-level, relationships to USAspending awards.

### Procurement

`SAM presolicitation → solicitation → award`

Primary keys: notice ID and solicitation number. Award linkage is only created when an exact solicitation/award identifier is observed; title similarity alone is insufficient.

### Spending

USAspending records the actual movement of federal money and closes the loop after grants and contracts are awarded.

## Join policy

1. Exact source/cross-source identifiers: automatic, high confidence.
2. Explicit official citations: automatic, high confidence once parsers exist.
3. Shared program/classification identifiers: related-context edges only; never identity.
4. Agency + title + date similarity: diagnostic candidate only, never automatic production linkage.
5. LLM/semantic similarity: not part of baseline identity resolution.

## Why this model

A single relational super-table would make fields ambiguous and encourage false joins. The event graph lets every source keep its native evidence while still building higher-order timelines.

The graph supports questions such as:

- Which OIRA-reviewed rules are drawing unusual stakeholder meeting activity?
- Which forecast grants became funded awards?
- Which agencies are increasing procurement in a NAICS market?
- Which laws are followed by regulatory implementation activity?
- Where is federal money moving after a policy change?

The answer remains auditable because every edge can explain exactly why two events were connected.
