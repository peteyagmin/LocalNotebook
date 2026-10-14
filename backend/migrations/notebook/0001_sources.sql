CREATE TABLE sources (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    type          TEXT NOT NULL,            -- pdf | docx | txt | md | text (pasted)
    original_name TEXT,
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    state         TEXT NOT NULL,            -- queued | processing | ready | failed
    stage         TEXT,
    progress      REAL NOT NULL DEFAULT 0,  -- 0..1
    error         TEXT,
    enabled       INTEGER NOT NULL DEFAULT 1,
    char_count    INTEGER,
    page_count    INTEGER,
    guide         TEXT,                     -- JSON: {"summary": str, "topics": [str]}
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE chunks (
    id         TEXT PRIMARY KEY,
    source_id  TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    ordinal    INTEGER NOT NULL,
    text       TEXT NOT NULL,
    char_start INTEGER NOT NULL,
    char_end   INTEGER NOT NULL,
    location   TEXT NOT NULL,               -- JSON: page, heading_path, char_start, char_end
    UNIQUE (source_id, ordinal)
);

CREATE VIRTUAL TABLE chunks_fts USING fts5(chunk_id UNINDEXED, source_id UNINDEXED, text);

CREATE TABLE notebook_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE jobs (
    id         TEXT PRIMARY KEY,
    kind       TEXT NOT NULL,               -- ingest
    source_id  TEXT,
    state      TEXT NOT NULL,               -- queued | running | succeeded | failed | interrupted
    progress   REAL NOT NULL DEFAULT 0,
    error      TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
