-- Audio overviews keep their choices (length, format) with the artifact so they can be regenerated.
ALTER TABLE artifacts ADD COLUMN options TEXT;  -- JSON
