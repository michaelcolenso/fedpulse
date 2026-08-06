-- FedPulse schema — SQLite
-- Core entity: a publication record from either feed (MARC from CGP, docs from FR API).

PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS records (
    -- unique id: 'marc:' + cgp record no, or 'fr:' + FR document number
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL CHECK (source IN ('marc', 'fr')),
    title TEXT,
    agency TEXT,               -- normalized agency name (110a/710a for marc; agencies[0].name for fr)
    agency_slug TEXT,          -- FR slug when available
    sudoc TEXT,                -- marc 086a (SuDoc call number)
    sudoc_stem TEXT,           -- top-level SuDoc class (e.g. "EP", "TD", "Y4")
    doc_type TEXT,             -- marc: bibliographic type from leader/006; fr: rule|proposed_rule|notice|presidential_document
    publication_date TEXT,     -- ISO yyyy-mm-dd (marc 008/06-14 or 260c/264c; fr publication_date)
    cataloged_date TEXT,       -- ISO yyyy-mm-dd when record appeared (marc: 005/008-00; fr: publication_date)
    url TEXT,                  -- marc 856u (PURL); fr: html_url
    subjects TEXT,             -- JSON array of 650 subject heading strings (marc); fr subjects/topics
    raw_json TEXT,             -- full original record (marc XML or fr JSON) for re-processing
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_records_agency_date ON records(agency, publication_date);
CREATE INDEX IF NOT EXISTS idx_records_sudoc_stem_date ON records(sudoc_stem, publication_date);
CREATE INDEX IF NOT EXISTS idx_records_type_date ON records(doc_type, publication_date);
CREATE INDEX IF NOT EXISTS idx_records_source ON records(source);
CREATE INDEX IF NOT EXISTS idx_records_cataloged_date ON records(cataloged_date);
CREATE INDEX IF NOT EXISTS idx_records_pub_date ON records(publication_date);

-- Ingest bookkeeping: what we loaded and when, so nightly runs are idempotent.
CREATE TABLE IF NOT EXISTS ingest_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    new_count INTEGER DEFAULT 0,
    changed_count INTEGER DEFAULT 0,
    deleted_count INTEGER DEFAULT 0,
    notes TEXT
);

-- Subject heading occurrence log (for TER emergence detection).
CREATE TABLE IF NOT EXISTS subject_first_seen (
    subject TEXT PRIMARY KEY,
    first_seen_date TEXT NOT NULL,
    first_record_id TEXT,
    first_agency TEXT
);
