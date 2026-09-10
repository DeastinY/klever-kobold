CREATE TABLE IF NOT EXISTS reports (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  received_at TEXT    NOT NULL DEFAULT (datetime('now')),
  question    TEXT    NOT NULL,
  answer      TEXT    NOT NULL,
  correction  TEXT    NOT NULL,
  source_url  TEXT,
  sources     TEXT,               -- JSON list of {name, url} the answer was built from
  model       TEXT,
  index_tag   TEXT,
  app         TEXT,
  ip_hash     TEXT                -- sha256 of the sender's IP, for rate limiting only
);
CREATE INDEX IF NOT EXISTS reports_received ON reports(received_at);
