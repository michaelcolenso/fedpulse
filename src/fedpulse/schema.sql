-- FedPulse SQLite schema. v0.2 is additive and idempotent.
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL CHECK (source IN ('marc', 'fr')),
    title TEXT, agency TEXT, agency_slug TEXT, sudoc TEXT, sudoc_stem TEXT,
    doc_type TEXT, publication_date TEXT, cataloged_date TEXT, url TEXT,
    subjects TEXT, raw_json TEXT,
    canonical_agency_id TEXT, canonical_agency_name TEXT,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_records_agency_date ON records(agency, publication_date);
CREATE INDEX IF NOT EXISTS idx_records_sudoc_stem_date ON records(sudoc_stem, publication_date);
CREATE INDEX IF NOT EXISTS idx_records_type_date ON records(doc_type, publication_date);
CREATE INDEX IF NOT EXISTS idx_records_source ON records(source);
CREATE INDEX IF NOT EXISTS idx_records_cataloged_date ON records(cataloged_date);
CREATE INDEX IF NOT EXISTS idx_records_pub_date ON records(publication_date);
CREATE INDEX IF NOT EXISTS idx_records_canonical_agency_date ON records(canonical_agency_id, publication_date);

CREATE TABLE IF NOT EXISTS ingest_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, started_at TEXT NOT NULL,
    finished_at TEXT, status TEXT NOT NULL DEFAULT 'running', new_count INTEGER DEFAULT 0,
    changed_count INTEGER DEFAULT 0, deleted_count INTEGER DEFAULT 0, notes TEXT
);
CREATE TABLE IF NOT EXISTS subject_first_seen (
    subject TEXT PRIMARY KEY, first_seen_date TEXT NOT NULL, first_record_id TEXT, first_agency TEXT
);
CREATE TABLE IF NOT EXISTS agency_aliases (
    source TEXT NOT NULL, raw_name TEXT NOT NULL, canonical_id TEXT NOT NULL,
    canonical_name TEXT NOT NULL, parent_id TEXT, mapping_method TEXT NOT NULL,
    PRIMARY KEY (source, raw_name)
);
CREATE INDEX IF NOT EXISTS idx_agency_aliases_canonical ON agency_aliases(canonical_id);

CREATE TABLE IF NOT EXISTS signal_state (
    signal_key TEXT PRIMARY KEY, signal_type TEXT NOT NULL, status TEXT NOT NULL,
    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL, last_notified TEXT,
    fingerprint TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS package_versions (
    package_version_id TEXT PRIMARY KEY, package_id TEXT NOT NULL,
    supersedes_version_id TEXT, created_at TEXT NOT NULL, direction TEXT NOT NULL,
    confidence TEXT NOT NULL, payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_package_versions_package ON package_versions(package_id, created_at);
CREATE TABLE IF NOT EXISTS package_version_records (
    package_version_id TEXT NOT NULL, record_id TEXT NOT NULL,
    PRIMARY KEY (package_version_id, record_id),
    FOREIGN KEY (package_version_id) REFERENCES package_versions(package_version_id) ON DELETE CASCADE,
    FOREIGN KEY (record_id) REFERENCES records(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_package_version_records_record ON package_version_records(record_id);
CREATE TABLE IF NOT EXISTS pipeline_state (
    component TEXT PRIMARY KEY, last_attempt TEXT, last_success TEXT,
    status TEXT NOT NULL, detail TEXT
);
