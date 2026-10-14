CREATE TABLE chat_messages (
    id          TEXT PRIMARY KEY,
    role        TEXT NOT NULL,                       -- user | assistant
    content     TEXT NOT NULL,
    citations   TEXT NOT NULL DEFAULT '[]',          -- JSON, snapshot of cited chunks (FR-3.2)
    suggestions TEXT NOT NULL DEFAULT '[]',          -- JSON list of follow-up questions
    status      TEXT NOT NULL DEFAULT 'complete',    -- complete | stopped | error
    created_at  TEXT NOT NULL
);
