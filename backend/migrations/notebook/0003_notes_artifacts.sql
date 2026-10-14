-- Jobs now cover more than ingestion: the target is a source, artifact, or note id.
ALTER TABLE jobs RENAME COLUMN source_id TO target_id;

CREATE TABLE notes (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    content    TEXT NOT NULL DEFAULT '',            -- Markdown; [n] markers refer to `citations`
    citations  TEXT NOT NULL DEFAULT '[]',          -- JSON snapshots of cited chunks (FR-4.1)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Notes are indexed like sources so search can be hybrid (FR-7.1).
CREATE TABLE note_chunks (
    id         TEXT PRIMARY KEY,
    note_id    TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    ordinal    INTEGER NOT NULL,
    text       TEXT NOT NULL,
    UNIQUE (note_id, ordinal)
);

CREATE VIRTUAL TABLE note_chunks_fts USING fts5(chunk_id UNINDEXED, note_id UNINDEXED, text);

CREATE TABLE artifacts (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,                      -- summary | briefing | study_guide | faq
    title       TEXT NOT NULL,
    state       TEXT NOT NULL,                      -- queued | running | ready | failed | cancelled
    stage       TEXT,
    progress    REAL NOT NULL DEFAULT 0,
    error       TEXT,
    focus       TEXT NOT NULL DEFAULT '',
    source_ids  TEXT NOT NULL DEFAULT '[]',         -- sources used (FR-5.13)
    citations   TEXT NOT NULL DEFAULT '[]',         -- JSON snapshots of cited chunks
    has_content INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
