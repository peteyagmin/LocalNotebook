-- Web pages, videos, audio and images (M5).
ALTER TABLE sources ADD COLUMN url TEXT;
ALTER TABLE sources ADD COLUMN fetched_at TEXT;
ALTER TABLE sources ADD COLUMN meta TEXT;          -- JSON: title, channel, description, duration...

-- Earlier captures of a web source (FR-2.9). The current capture is the sources row itself;
-- its predecessors are archived under sources/<id>/versions/<version>/.
CREATE TABLE source_versions (
    id         TEXT PRIMARY KEY,
    source_id  TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    version    INTEGER NOT NULL,
    fetched_at TEXT,
    char_count INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE (source_id, version)
);
