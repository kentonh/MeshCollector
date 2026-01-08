"""
FastAPI ingest server for federated Meshtastic system.
Receives and stores events from distributed collectors.
"""

import os
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field
import asyncpg


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Pydantic models
class Event(BaseModel):
    """Individual event in a batch."""
    event_id: str
    event_type: str
    observed_at: datetime
    payload: Dict[str, Any]


class Batch(BaseModel):
    """Batch of events from a collector."""
    schema_version: int
    collector_id: str
    sent_at: datetime
    events: List[Event]


class IngestResponse(BaseModel):
    """Response to batch ingest request."""
    accepted: List[str]
    rejected: List[Dict[str, str]] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    database: str


class StatsResponse(BaseModel):
    """Statistics response."""
    total_events: int
    total_nodes: int
    total_packets: int
    collectors: List[Dict[str, Any]]


# FastAPI app
app = FastAPI(
    title="Federated Meshtastic Ingest API",
    description="Central API for collecting Meshtastic data from distributed collectors",
    version="1.0.0"
)

# Middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
pool: Optional[asyncpg.Pool] = None

# Collector tokens (load from environment in production)
TOKENS = {}


def load_tokens():
    """Load collector tokens from environment."""
    global TOKENS
    # Format: COLLECTOR_TOKEN_<collector_id>=<token>
    for key, value in os.environ.items():
        if key.startswith('COLLECTOR_TOKEN_'):
            collector_id = key.replace('COLLECTOR_TOKEN_', '').lower().replace('_', '-')
            TOKENS[collector_id] = value

    logger.info(f"Loaded {len(TOKENS)} collector tokens")


@app.on_event("startup")
async def startup():
    """Initialize database connection pool."""
    global pool

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        raise RuntimeError("DATABASE_URL not configured")

    logger.info("Connecting to database...")
    pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10)
    logger.info("Database connection pool created")

    # Ensure schema exists
    async with pool.acquire() as conn:
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        if os.path.exists(schema_path):
            with open(schema_path, 'r') as f:
                await conn.execute(f.read())
            logger.info("Database schema initialized")

    # Load collector tokens
    load_tokens()


@app.on_event("shutdown")
async def shutdown():
    """Close database connection pool."""
    global pool
    if pool:
        await pool.close()
        logger.info("Database connection pool closed")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    db_status = "connected" if pool else "disconnected"
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        database=db_status
    )


@app.get("/v1/stats", response_model=StatsResponse)
async def get_stats():
    """Get system statistics."""
    if not pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with pool.acquire() as conn:
        total_events = await conn.fetchval("SELECT COUNT(*) FROM events_raw")
        total_nodes = await conn.fetchval("SELECT COUNT(*) FROM nodes")
        total_packets = await conn.fetchval("SELECT COUNT(*) FROM packets")

        # Get collector stats
        collector_rows = await conn.fetch("""
            SELECT
                collector_id,
                COUNT(*) as event_count,
                MAX(received_at) as last_upload
            FROM events_raw
            GROUP BY collector_id
            ORDER BY last_upload DESC
        """)

        collectors = [
            {
                'collector_id': row['collector_id'],
                'event_count': row['event_count'],
                'last_upload': row['last_upload'].isoformat() if row['last_upload'] else None
            }
            for row in collector_rows
        ]

    return StatsResponse(
        total_events=total_events or 0,
        total_nodes=total_nodes or 0,
        total_packets=total_packets or 0,
        collectors=collectors
    )


@app.post("/v1/ingest/batch", response_model=IngestResponse)
async def ingest_batch(
    batch: Batch,
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """
    Ingest a batch of events from a collector.

    Requires Bearer token authentication matching the collector_id.
    """
    # Validate schema version
    if batch.schema_version != 1:
        raise HTTPException(status_code=400, detail="Unsupported schema_version")

    # Authenticate collector
    token = (authorization or "").replace("Bearer ", "").strip()
    expected_token = TOKENS.get(batch.collector_id)

    if not expected_token or token != expected_token:
        logger.warning(f"Unauthorized ingest attempt for collector '{batch.collector_id}' from {request.client.host}")
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not pool:
        raise HTTPException(status_code=503, detail="Database not available")

    logger.info(f"Received batch from '{batch.collector_id}' with {len(batch.events)} events")

    accepted = []
    rejected = []

    async with pool.acquire() as conn:
        async with conn.transaction():
            for event in batch.events:
                try:
                    # Insert into events_raw table
                    await conn.execute(
                        """
                        INSERT INTO events_raw (event_id, collector_id, event_type, observed_at, payload)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (event_id) DO NOTHING
                        """,
                        event.event_id,
                        batch.collector_id,
                        event.event_type,
                        event.observed_at,
                        event.payload
                    )
                    accepted.append(event.event_id)

                except Exception as e:
                    logger.error(f"Failed to insert event {event.event_id}: {e}")
                    rejected.append({
                        "event_id": event.event_id,
                        "reason": "insert_failed"
                    })

    logger.info(f"Batch processed: {len(accepted)} accepted, {len(rejected)} rejected")

    return IngestResponse(accepted=accepted, rejected=rejected)


@app.get("/v1/nodes")
async def get_nodes(
    limit: int = 100,
    offset: int = 0,
    has_position: Optional[bool] = None
):
    """
    Get list of nodes.

    Query parameters:
    - limit: Maximum number of nodes to return (default: 100)
    - offset: Offset for pagination (default: 0)
    - has_position: Filter nodes with/without position data
    """
    if not pool:
        raise HTTPException(status_code=503, detail="Database not available")

    query = "SELECT * FROM nodes"
    params = []

    if has_position is not None:
        if has_position:
            query += " WHERE latitude IS NOT NULL AND longitude IS NOT NULL"
        else:
            query += " WHERE latitude IS NULL OR longitude IS NULL"

    query += " ORDER BY last_seen DESC LIMIT $1 OFFSET $2"
    params.extend([limit, offset])

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        nodes = [dict(row) for row in rows]

    return {"nodes": nodes, "count": len(nodes)}


@app.get("/v1/nodes/{node_id}")
async def get_node(node_id: str):
    """Get details for a specific node."""
    if not pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with pool.acquire() as conn:
        node = await conn.fetchrow("SELECT * FROM nodes WHERE node_id = $1", node_id)
        if not node:
            raise HTTPException(status_code=404, detail="Node not found")

        # Get recent observations
        observations = await conn.fetch(
            """
            SELECT * FROM node_observations
            WHERE node_id = $1
            ORDER BY observed_at DESC
            LIMIT 50
            """,
            node_id
        )

        return {
            "node": dict(node),
            "observations": [dict(obs) for obs in observations]
        }


@app.get("/v1/map/geojson")
async def get_map_geojson(
    min_lat: Optional[float] = None,
    max_lat: Optional[float] = None,
    min_lon: Optional[float] = None,
    max_lon: Optional[float] = None,
    hours: int = 24
):
    """
    Get nodes as GeoJSON for map display.

    Query parameters:
    - min_lat, max_lat, min_lon, max_lon: Bounding box filter
    - hours: Only include nodes seen in last N hours (default: 24)
    """
    if not pool:
        raise HTTPException(status_code=503, detail="Database not available")

    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(hours=hours)

    query = """
        SELECT
            node_id, short_name, long_name, hardware, role,
            last_seen, latitude, longitude, altitude, battery_level
        FROM nodes
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        AND last_seen > $1
    """
    params = [cutoff]
    param_num = 2

    # Add bounding box filters
    if min_lat is not None:
        query += f" AND latitude >= ${param_num}"
        params.append(min_lat)
        param_num += 1
    if max_lat is not None:
        query += f" AND latitude <= ${param_num}"
        params.append(max_lat)
        param_num += 1
    if min_lon is not None:
        query += f" AND longitude >= ${param_num}"
        params.append(min_lon)
        param_num += 1
    if max_lon is not None:
        query += f" AND longitude <= ${param_num}"
        params.append(max_lon)
        param_num += 1

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)

        features = []
        for row in rows:
            # Calculate status based on last_seen
            now = datetime.utcnow()
            time_diff = (now - row['last_seen'].replace(tzinfo=None)).total_seconds()

            if time_diff < 300:  # 5 minutes
                status = "online"
            elif time_diff < 3600:  # 1 hour
                status = "recent"
            elif time_diff < 86400:  # 24 hours
                status = "stale"
            else:
                status = "offline"

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [row['longitude'], row['latitude']]
                },
                "properties": {
                    "node_id": row['node_id'],
                    "short_name": row['short_name'],
                    "long_name": row['long_name'],
                    "hardware": row['hardware'],
                    "role": row['role'],
                    "last_seen": row['last_seen'].isoformat() if row['last_seen'] else None,
                    "altitude": row['altitude'],
                    "battery_level": row['battery_level'],
                    "status": status
                }
            })

        return {
            "type": "FeatureCollection",
            "features": features
        }


@app.get("/v1/traceroutes")
async def get_traceroutes(
    source_node: Optional[str] = None,
    dest_node: Optional[str] = None,
    limit: int = 100
):
    """
    Get traceroute data.

    Query parameters:
    - source_node: Filter by source node
    - dest_node: Filter by destination node
    - limit: Maximum number of traces to return
    """
    if not pool:
        raise HTTPException(status_code=503, detail="Database not available")

    query = """
        SELECT
            trace_id, source_node, dest_node,
            MIN(observed_at) as first_seen,
            MAX(observed_at) as last_seen,
            COUNT(*) as hop_count
        FROM trace_events
        WHERE 1=1
    """
    params = []
    param_num = 1

    if source_node:
        query += f" AND source_node = ${param_num}"
        params.append(source_node)
        param_num += 1

    if dest_node:
        query += f" AND dest_node = ${param_num}"
        params.append(dest_node)
        param_num += 1

    query += f" GROUP BY trace_id, source_node, dest_node ORDER BY last_seen DESC LIMIT ${param_num}"
    params.append(limit)

    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
        traces = [dict(row) for row in rows]

    return {"traces": traces, "count": len(traces)}


@app.get("/v1/traceroutes/{trace_id}")
async def get_traceroute_detail(trace_id: str):
    """Get detailed hop information for a specific trace."""
    if not pool:
        raise HTTPException(status_code=503, detail="Database not available")

    async with pool.acquire() as conn:
        hops = await conn.fetch(
            """
            SELECT * FROM trace_events
            WHERE trace_id = $1
            ORDER BY hop_number
            """,
            trace_id
        )

        if not hops:
            raise HTTPException(status_code=404, detail="Trace not found")

        return {
            "trace_id": trace_id,
            "source_node": hops[0]['source_node'],
            "dest_node": hops[0]['dest_node'],
            "hops": [dict(hop) for hop in hops]
        }


@app.get("/v1/topology")
async def get_topology(hours: int = 24):
    """
    Get network topology data for graph visualization.

    Returns nodes and links based on relay relationships.

    Query parameters:
    - hours: Only include data from last N hours (default: 24)
    """
    if not pool:
        raise HTTPException(status_code=503, detail="Database not available")

    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(hours=hours)

    async with pool.acquire() as conn:
        # Get all active nodes
        nodes = await conn.fetch(
            """
            SELECT
                node_id, short_name, long_name, hardware, role,
                latitude, longitude, last_seen
            FROM nodes
            WHERE last_seen > $1
            ORDER BY last_seen DESC
            """,
            cutoff
        )

        # Get relay relationships from packets
        links = await conn.fetch(
            """
            SELECT
                from_node as source,
                relay_node as target,
                COUNT(*) as packet_count,
                AVG(rssi) as avg_rssi,
                AVG(snr) as avg_snr
            FROM packets
            WHERE relay_node IS NOT NULL
            AND received_at > $1
            GROUP BY from_node, relay_node
            """,
            cutoff
        )

        # Also get direct observations (non-relay connections)
        observations = await conn.fetch(
            """
            SELECT
                node_id as source,
                observer_id as target,
                COUNT(*) as observation_count,
                AVG(rssi) as avg_rssi,
                AVG(snr) as avg_snr
            FROM node_observations
            WHERE observed_at > $1
            AND metadata->>'relay' IS NULL
            GROUP BY node_id, observer_id
            """,
            cutoff
        )

        return {
            "nodes": [dict(node) for node in nodes],
            "links": [dict(link) for link in links],
            "observations": [dict(obs) for obs in observations]
        }


@app.get("/v1/network-stats")
async def get_network_stats(hours: int = 24):
    """
    Get detailed network statistics.

    Query parameters:
    - hours: Time window for statistics (default: 24)
    """
    if not pool:
        raise HTTPException(status_code=503, detail="Database not available")

    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(hours=hours)

    async with pool.acquire() as conn:
        # Active nodes
        active_nodes = await conn.fetchval(
            "SELECT COUNT(*) FROM nodes WHERE last_seen > $1", cutoff
        )

        # Nodes with position
        nodes_with_position = await conn.fetchval(
            """
            SELECT COUNT(*) FROM nodes
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            AND last_seen > $1
            """,
            cutoff
        )

        # Packets in time window
        packets_count = await conn.fetchval(
            "SELECT COUNT(*) FROM packets WHERE received_at > $1", cutoff
        )

        # Top relay nodes
        top_relays = await conn.fetch(
            """
            SELECT
                relay_node as node_id,
                COUNT(*) as relay_count
            FROM packets
            WHERE relay_node IS NOT NULL
            AND received_at > $1
            GROUP BY relay_node
            ORDER BY relay_count DESC
            LIMIT 10
            """,
            cutoff
        )

        # Collector health
        collector_health = await conn.fetch(
            """
            SELECT
                collector_id,
                MAX(timestamp) as last_report,
                MAX(packets_rx) as packets_rx,
                MAX(unique_nodes) as unique_nodes
            FROM collector_stats
            WHERE timestamp > $1
            GROUP BY collector_id
            ORDER BY last_report DESC
            """,
            cutoff
        )

        return {
            "time_window_hours": hours,
            "active_nodes": active_nodes or 0,
            "nodes_with_position": nodes_with_position or 0,
            "total_packets": packets_count or 0,
            "top_relay_nodes": [dict(r) for r in top_relays],
            "collectors": [dict(c) for c in collector_health]
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
