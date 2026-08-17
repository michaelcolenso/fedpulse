# FedPulse embedding retrieval

## Purpose

Embeddings are a **candidate retrieval mechanism**, never evidence. They help FedPulse find semantically relevant records whose language does not overlap literally with a watch profile. Structured source facts still control geography, eligibility, lifecycle status, deadlines, amounts, identifiers, and final verification.

## Production path

1. Deterministic hard eligibility narrows the government corpus.
2. `canonical_event_text()` creates a source-aware retrieval document.
3. Workers AI `@cf/qwen/qwen3-embedding-0.6b` embeds the document.
4. Vectorize index `fedpulse-opportunities-v1` stores the vector with minimal metadata.
5. `canonical_profile_text()` is embedded as the query.
6. Vectorize returns semantic candidates.
7. Existing deterministic scoring reranks candidates using authoritative structured evidence.
8. Optional v0.5 analyst/skeptic LLM operates only on the final small candidate set.
9. If Workers AI or Vectorize is unavailable, FedPulse uses `semantic.py` deterministic semantic retrieval unchanged.

The index uses 1024 dimensions and cosine distance to match Qwen3-Embedding-0.6B. The index configuration is immutable; changing embedding model/dimensions requires a new versioned index name.

## Canonical representations

### SAM.gov contracts

Embed:
- title
- agency
- notice/lifecycle type
- **place of performance only** (not contracting-office/contact geography)
- NAICS
- set-aside
- response deadline
- solicitation number
- description/synopsis

Do not treat semantic location similarity as geographic evidence. `PopCity`/`PopState` remain the authoritative geographic fields.

### Grants.gov

Embed:
- title
- agency
- forecast/opportunity stage
- opportunity number
- Assistance Listing/CFDA
- eligible applicants
- estimated funding/award ceiling when present
- close date
- synopsis/description

Eligibility and dollar thresholds remain structured filters.

### OIRA / RegInfo

Embed:
- regulatory action title
- agency
- RIN
- review/meeting stage
- meeting topic
- participant/organization names when present
- description

RIN remains the authoritative cross-source identity key.

### Federal Register

Embed:
- title
- agency
- document type
- RIN
- docket ID
- action text
- abstract/description

RIN/docket joins remain deterministic. Embedding similarity may suggest related records but cannot create a `same_government_action` edge by itself.

### Congressional Bill Status

Embed:
- bill title
- bill ID/number
- Congress
- policy area
- latest action
- summary

Bill identity and statutory links remain deterministic identifiers.

### USAspending awards

Embed:
- transaction/award description
- awarding agency
- recipient
- award ID
- NAICS
- place of performance
- transaction type/stage

Transaction amount/date remain authoritative structured facts and are not inferred from text.

## Profile representation

A watch profile becomes a short semantic query document containing its human-readable label, capabilities/topics, desired geographies, relevant agencies, and NAICS codes. Embedding similarity broadens vocabulary; deterministic rules still enforce hard profile requirements such as the PNW profile requiring actual geographic evidence.

## Indexing policy

- Hash canonical text; only re-embed when the hash or embedding model version changes.
- Upsert rather than insert so corrected source normalization replaces stale vectors.
- Keep vector metadata small: event ID, source, kind, profile/namespace where applicable, and canonical-text hash.
- Use namespaces if later needed to isolate corpus generations or source families.
- Never store an LLM conclusion as vector metadata evidence.

## Failure behavior

Workers AI/Vectorize is optional intelligence infrastructure. Any inference, index, network, or binding failure falls back to the deterministic semantic scorer. Nightly source ingestion and publication must remain successful without embeddings.

## Evaluation

For every profile compare:
- deterministic semantic top 100
- embedding top 100
- deterministic final rank
- hybrid LLM final rank

Track precision@5/10, useful promotions, false-positive removals, semantic-only discoveries, disagreement rate, embedding cost, and cost per useful discovery. Do not enable embedding influence on production recommendations until it improves the labeled evaluation set.
