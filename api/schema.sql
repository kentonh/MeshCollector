-- Central database schema for federated Meshtastic system
-- PostgreSQL

-- Raw events table for audit and reprocessing
CREATE TABLE IF NOT EXISTS events_raw (
  event_id      text PRIMARY KEY,
  collector_id  text NOT NULL,
  event_type    text NOT NULL,
  observed_at   timestamptz NOT NULL,
  received_at   timestamptz NOT NULL DEFAULT now(),
  payload       jsonb NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_raw_observed_at
  ON events_raw(observed_at);

CREATE INDEX IF NOT EXISTS idx_events_raw_type_time
  ON events_raw(event_type, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_events_raw_collector
  ON events_raw(collector_id, observed_at DESC);

-- Normalized nodes table
CREATE TABLE IF NOT EXISTS nodes (
  node_id       text PRIMARY KEY,
  short_name    text,
  long_name     text,
  hardware      text,
  role          text,
  first_seen    timestamptz NOT NULL,
  last_seen     timestamptz NOT NULL,
  latitude      double precision,
  longitude     double precision,
  altitude      integer,
  battery_level integer,
  metadata      jsonb
);

CREATE INDEX IF NOT EXISTS idx_nodes_last_seen
  ON nodes(last_seen DESC);

CREATE INDEX IF NOT EXISTS idx_nodes_location
  ON nodes(latitude, longitude) WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

-- Node observations (for tracking who saw which node)
CREATE TABLE IF NOT EXISTS node_observations (
  id            bigserial PRIMARY KEY,
  node_id       text NOT NULL,
  observer_id   text NOT NULL,              -- collector_id or gateway node
  observed_at   timestamptz NOT NULL,
  rssi          integer,
  snr           real,
  hop_limit     integer,
  metadata      jsonb
);

CREATE INDEX IF NOT EXISTS idx_node_obs_node_time
  ON node_observations(node_id, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_node_obs_observer_time
  ON node_observations(observer_id, observed_at DESC);

-- Packets table for detailed packet tracking
CREATE TABLE IF NOT EXISTS packets (
  id            bigserial PRIMARY KEY,
  packet_id     bigint NOT NULL,
  from_node     text NOT NULL,
  to_node       text NOT NULL,
  received_at   timestamptz NOT NULL,
  channel       integer,
  port_num      text,
  hop_limit     integer,
  hop_start     integer,
  rssi          integer,
  snr           real,
  relay_node    text,                       -- node that relayed this packet
  collector_id  text NOT NULL,
  payload_type  text,
  payload       jsonb
);

CREATE INDEX IF NOT EXISTS idx_packets_from_node
  ON packets(from_node, received_at DESC);

CREATE INDEX IF NOT EXISTS idx_packets_to_node
  ON packets(to_node, received_at DESC);

CREATE INDEX IF NOT EXISTS idx_packets_relay_node
  ON packets(relay_node, received_at DESC) WHERE relay_node IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_packets_collector
  ON packets(collector_id, received_at DESC);

-- Traceroute events for route tracking
CREATE TABLE IF NOT EXISTS trace_events (
  id            bigserial PRIMARY KEY,
  trace_id      text NOT NULL,               -- unique trace identifier
  source_node   text NOT NULL,
  dest_node     text NOT NULL,
  hop_number    integer NOT NULL,
  hop_node      text NOT NULL,
  observed_at   timestamptz NOT NULL,
  rssi          integer,
  snr           real,
  collector_id  text NOT NULL,
  metadata      jsonb
);

CREATE INDEX IF NOT EXISTS idx_trace_events_trace_id
  ON trace_events(trace_id, hop_number);

CREATE INDEX IF NOT EXISTS idx_trace_events_route
  ON trace_events(source_node, dest_node, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_trace_events_collector
  ON trace_events(collector_id, observed_at DESC);

-- Collector health metrics
CREATE TABLE IF NOT EXISTS collector_stats (
  collector_id  text NOT NULL,
  timestamp     timestamptz NOT NULL,
  packets_rx    integer,
  unique_nodes  integer,
  uptime_seconds bigint,
  version       text,
  metadata      jsonb,
  PRIMARY KEY (collector_id, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_collector_stats_time
  ON collector_stats(timestamp DESC);
