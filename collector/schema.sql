-- Outbox table for reliable data uploads to central API
-- This implements the outbox pattern for durable message queuing

CREATE TABLE IF NOT EXISTS outbox (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id      TEXT NOT NULL UNIQUE,         -- stable ID for dedupe (sha256 hash)
  collector_id  TEXT NOT NULL,                -- identifier for this collector
  event_type    TEXT NOT NULL,                -- type of event (packet, node_observation, trace_event)
  created_at    INTEGER NOT NULL,             -- unix timestamp when event was created
  payload_json  TEXT NOT NULL,                -- JSON payload of the event
  attempts      INTEGER NOT NULL DEFAULT 0,   -- number of upload attempts
  next_attempt  INTEGER NOT NULL DEFAULT 0,   -- unix timestamp when next attempt should occur
  sent_at       INTEGER                       -- unix timestamp when successfully sent (NULL if not sent)
);

CREATE INDEX IF NOT EXISTS idx_outbox_unsent
  ON outbox(sent_at, next_attempt);

CREATE INDEX IF NOT EXISTS idx_outbox_collector
  ON outbox(collector_id);

CREATE INDEX IF NOT EXISTS idx_outbox_event_type
  ON outbox(event_type);
