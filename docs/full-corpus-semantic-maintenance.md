# Full-corpus semantic maintenance

FedPulse semantic maintenance now distinguishes corpus coverage from per-run throughput.

- The eligible corpus is every `contract_opportunity` and `funding_opportunity` in `government_events` unless an operator explicitly supplies `--limit` for sampling or smoke tests.
- Every eligible record is canonicalized and fingerprinted each run.
- Only new or changed fingerprints are candidates for Workers AI embedding.
- `--max-updates` is a throughput guard, not a corpus cutoff. Deferred records remain uncommitted and therefore remain in the changed backlog on the next run.
- Fingerprints are committed only after Vectorize upsert succeeds.
- Nightly currently uses `--max-updates 2500` while production timing is calibrated.

Nightly stats report `eligible`, `changed_total`, `documents` (scheduled), `unchanged`, and `deferred` so backlog convergence is observable.
