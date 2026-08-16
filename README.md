# FedPulse

FedPulse is an evidence-ranked federal activity monitoring system. It combines Federal Register, GPO, OIRA/RegInfo, Grants.gov, SAM.gov, USAspending, and Congressional bulk data into deterministic, source-backed signals.

## Product surfaces

- **Today** — concise executive brief of federal developments worth attention.
- **Opportunities Today** — fresh government actions ranked against deterministic watch profiles.
- **Act Now** — open contracts and funding where action can still affect the outcome.
- **Market Intelligence** — awards and spending activity that reveal where demand and federal money are moving.
- **Policy Signals** — legislation, OIRA activity, and upstream regulatory actions.
- **Evidence Explorer** — detailed supporting records and diagnostics.

## Opportunity ranking

FedPulse does not rank opportunities by keyword match or dollar size alone. Every surfaced item receives an explainable component score covering:

- freshness of the official action;
- novelty (`first_seen`) in the FedPulse corpus;
- profile relevance across topic, geography, NAICS, and agency;
- multi-factor specificity;
- deadline urgency and useful response runway;
- commercial magnitude;
- early-stage advantage such as forecast, Sources Sought, and presolicitation notices;
- competition signals such as small-business and restricted set-asides;
- actionability by event type.

Items that are both upstream and specifically matched can be labeled **early signal** and sort ahead of otherwise higher-volume generic activity. The component breakdown is retained in `opportunities_today.json` and exposed in the dashboard so every ranking remains auditable.

## Watch profiles

Current deterministic profiles include:

- Construction / AEC / Washington
- AI / Technology
- Business Opportunities
- Seattle / Pacific Northwest Intelligence

Profiles are plain JSON configuration—no user account or LLM is required.

## Design principles

1. Official-source evidence first.
2. No required source API keys for the baseline pipeline.
3. Separate clocks for sources with different publication cadences.
4. Atomic, generation-based publication.
5. Quiet states are valid output; weak evidence should not become an alert.
6. Relevance and evidence confidence are separate concepts.
7. Every ranking should be explainable from deterministic inputs.

## Runtime

The core pipeline is stdlib-only Python + SQLite. The dashboard is dependency-free HTML/CSS/JavaScript served by Cloudflare Workers Static Assets, with generated snapshots stored in Cloudflare KV.
