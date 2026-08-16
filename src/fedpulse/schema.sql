-- FedPulse SQLite schema. v0.4 remains additive and idempotent.
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL CHECK (source IN ('marc', 'fr')),
    title TEXT, agency TEXT, agency_slug TEXT, sudoc TEXT, sudoc_stem TEXT,
    doc_type TEXT, publication_date TEXT, cataloged_date TEXT, url TEXT,
    subjects TEXT, raw_json TEXT,
    canonical_agency_id TEXT, canonical_agency_name TEXT, agency_mapping_version TEXT,
    created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_records_agency_date ON records(agency, publication_date);
CREATE INDEX IF NOT EXISTS idx_records_sudoc_stem_date ON records(sudoc_stem, publication_date);
CREATE INDEX IF NOT EXISTS idx_records_type_date ON records(doc_type, publication_date);
CREATE INDEX IF NOT EXISTS idx_records_source ON records(source);
CREATE INDEX IF NOT EXISTS idx_records_cataloged_date ON records(cataloged_date);
CREATE INDEX IF NOT EXISTS idx_records_pub_date ON records(publication_date);
CREATE INDEX IF NOT EXISTS idx_records_canonical_agency_date ON records(canonical_agency_id, publication_date);
CREATE INDEX IF NOT EXISTS idx_records_mapping_version ON records(agency_mapping_version, id);

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

-- v0.4 government-action graph. New source families live here rather than being
-- forced into the regulatory records table above.
CREATE TABLE IF NOT EXISTS government_events (
    event_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    stage TEXT,
    title TEXT,
    agency TEXT,
    event_date TEXT,
    amount REAL,
    currency TEXT,
    official_url TEXT,
    payload_json TEXT NOT NULL,
    content_sha256 TEXT,
    first_seen TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_government_events_source_date ON government_events(source, event_date);
CREATE INDEX IF NOT EXISTS idx_government_events_kind_date ON government_events(kind, event_date);
CREATE INDEX IF NOT EXISTS idx_government_events_agency ON government_events(agency);

CREATE TABLE IF NOT EXISTS government_identifiers (
    event_id TEXT NOT NULL,
    namespace TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (event_id, namespace, value),
    FOREIGN KEY (event_id) REFERENCES government_events(event_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_government_identifiers_lookup ON government_identifiers(namespace, value);

CREATE TABLE IF NOT EXISTS government_edges (
    from_event_id TEXT NOT NULL,
    to_event_id TEXT NOT NULL,
    relationship TEXT NOT NULL,
    method TEXT NOT NULL,
    confidence TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (from_event_id, to_event_id, relationship),
    FOREIGN KEY (from_event_id) REFERENCES government_events(event_id) ON DELETE CASCADE,
    FOREIGN KEY (to_event_id) REFERENCES government_events(event_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_government_edges_to ON government_edges(to_event_id);

CREATE TABLE IF NOT EXISTS source_cursors (
    source TEXT PRIMARY KEY,
    cursor TEXT,
    content_sha256 TEXT,
    last_success TEXT,
    detail TEXT
);
