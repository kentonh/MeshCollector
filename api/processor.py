#!/usr/bin/env python3
"""
Background data processor for federated Meshtastic system.
Normalizes events_raw into domain tables (nodes, packets, trace_events, etc.)
"""

import os
import sys
import logging
import argparse
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

import asyncpg


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DataProcessor:
    """Processes raw events into normalized tables."""

    def __init__(self, database_url: str):
        """Initialize processor with database connection."""
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Establish database connection pool."""
        logger.info("Connecting to database...")
        self.pool = await asyncpg.create_pool(self.database_url, min_size=2, max_size=5)
        logger.info("Database connection established")

    async def close(self):
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection closed")

    async def process_packet_event(self, event_id: str, collector_id: str,
                                   observed_at: datetime, payload: Dict[str, Any]):
        """
        Process a packet event into nodes and packets tables.

        Args:
            event_id: Unique event identifier
            collector_id: Collector that captured this packet
            observed_at: Timestamp when packet was observed
            payload: Packet data
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Extract packet fields
                packet_id = payload.get('packet_id')
                from_node = payload.get('from_node')
                to_node = payload.get('to_node')
                channel = payload.get('channel')
                port_num = payload.get('port_num')
                hop_limit = payload.get('hop_limit')
                hop_start = payload.get('hop_start')
                rssi = payload.get('rssi')
                snr = payload.get('snr')
                relay_node = payload.get('relay_node')

                # Update or create source node
                if from_node:
                    await self._upsert_node(
                        conn, from_node, observed_at, payload.get('from_node_info', {})
                    )

                # Update or create destination node
                if to_node and to_node != '^all':
                    await self._upsert_node(
                        conn, to_node, observed_at, payload.get('to_node_info', {})
                    )

                # Record node observation by collector
                if from_node:
                    await conn.execute(
                        """
                        INSERT INTO node_observations
                        (node_id, observer_id, observed_at, rssi, snr, hop_limit, metadata)
                        VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """,
                        from_node, collector_id, observed_at, rssi, snr, hop_limit,
                        {'event_id': event_id}
                    )

                # Insert packet
                if packet_id:
                    await conn.execute(
                        """
                        INSERT INTO packets
                        (packet_id, from_node, to_node, received_at, channel, port_num,
                         hop_limit, hop_start, rssi, snr, relay_node, collector_id,
                         payload_type, payload)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                        ON CONFLICT DO NOTHING
                        """,
                        packet_id, from_node, to_node, observed_at, channel, port_num,
                        hop_limit, hop_start, rssi, snr, relay_node, collector_id,
                        payload.get('type'), payload
                    )

                # Process relay node for topography
                if relay_node and relay_node != from_node:
                    # This packet was relayed, which gives us topology information
                    await self._upsert_node(conn, relay_node, observed_at, {})

                    # Record that relay_node relayed for from_node
                    await conn.execute(
                        """
                        INSERT INTO node_observations
                        (node_id, observer_id, observed_at, metadata)
                        VALUES ($1, $2, $3, $4)
                        """,
                        relay_node, from_node, observed_at,
                        {'relay': True, 'event_id': event_id}
                    )

    async def _upsert_node(self, conn, node_id: str, observed_at: datetime,
                          node_info: Dict[str, Any]):
        """
        Insert or update node information.

        Args:
            conn: Database connection
            node_id: Node identifier
            observed_at: Observation timestamp
            node_info: Node metadata (position, hardware, etc.)
        """
        # Extract node fields
        short_name = node_info.get('short_name')
        long_name = node_info.get('long_name')
        hardware = node_info.get('hardware')
        role = node_info.get('role')
        latitude = node_info.get('latitude')
        longitude = node_info.get('longitude')
        altitude = node_info.get('altitude')
        battery_level = node_info.get('battery_level')

        # Check if node exists
        existing = await conn.fetchrow(
            "SELECT first_seen, last_seen FROM nodes WHERE node_id = $1", node_id
        )

        if existing:
            # Update existing node (only update last_seen and optional fields if provided)
            update_fields = ['last_seen = $2']
            params = [node_id, observed_at]
            param_num = 3

            if short_name:
                update_fields.append(f'short_name = ${param_num}')
                params.append(short_name)
                param_num += 1

            if long_name:
                update_fields.append(f'long_name = ${param_num}')
                params.append(long_name)
                param_num += 1

            if hardware:
                update_fields.append(f'hardware = ${param_num}')
                params.append(hardware)
                param_num += 1

            if role:
                update_fields.append(f'role = ${param_num}')
                params.append(role)
                param_num += 1

            if latitude is not None and longitude is not None:
                update_fields.append(f'latitude = ${param_num}')
                params.append(latitude)
                param_num += 1
                update_fields.append(f'longitude = ${param_num}')
                params.append(longitude)
                param_num += 1

            if altitude is not None:
                update_fields.append(f'altitude = ${param_num}')
                params.append(altitude)
                param_num += 1

            if battery_level is not None:
                update_fields.append(f'battery_level = ${param_num}')
                params.append(battery_level)
                param_num += 1

            query = f"UPDATE nodes SET {', '.join(update_fields)} WHERE node_id = $1"
            await conn.execute(query, *params)
        else:
            # Insert new node
            await conn.execute(
                """
                INSERT INTO nodes
                (node_id, short_name, long_name, hardware, role, first_seen, last_seen,
                 latitude, longitude, altitude, battery_level, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                """,
                node_id, short_name, long_name, hardware, role, observed_at, observed_at,
                latitude, longitude, altitude, battery_level, node_info
            )

    async def process_trace_event(self, event_id: str, collector_id: str,
                                  observed_at: datetime, payload: Dict[str, Any]):
        """
        Process a traceroute event.

        Args:
            event_id: Unique event identifier
            collector_id: Collector that captured this trace
            observed_at: Timestamp when trace was observed
            payload: Trace data
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                trace_id = payload.get('trace_id')
                source_node = payload.get('source_node')
                dest_node = payload.get('dest_node')
                hops = payload.get('hops', [])

                for hop_num, hop in enumerate(hops):
                    hop_node = hop.get('node_id')
                    rssi = hop.get('rssi')
                    snr = hop.get('snr')

                    if hop_node:
                        await conn.execute(
                            """
                            INSERT INTO trace_events
                            (trace_id, source_node, dest_node, hop_number, hop_node,
                             observed_at, rssi, snr, collector_id, metadata)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                            """,
                            trace_id, source_node, dest_node, hop_num, hop_node,
                            observed_at, rssi, snr, collector_id, hop
                        )

    async def process_collector_stats(self, event_id: str, collector_id: str,
                                      observed_at: datetime, payload: Dict[str, Any]):
        """
        Process collector health statistics.

        Args:
            event_id: Unique event identifier
            collector_id: Collector identifier
            observed_at: Timestamp
            payload: Stats data
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO collector_stats
                (collector_id, timestamp, packets_rx, unique_nodes, uptime_seconds,
                 version, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (collector_id, timestamp) DO NOTHING
                """,
                collector_id, observed_at,
                payload.get('packets_rx'),
                payload.get('unique_nodes'),
                payload.get('uptime_seconds'),
                payload.get('version'),
                payload
            )

    async def process_batch(self, batch_size: int = 1000) -> int:
        """
        Process a batch of unprocessed events.

        Args:
            batch_size: Number of events to process

        Returns:
            Number of events processed
        """
        async with self.pool.acquire() as conn:
            # Find oldest unprocessed events
            rows = await conn.fetch(
                """
                SELECT event_id, collector_id, event_type, observed_at, payload
                FROM events_raw
                WHERE event_id NOT IN (
                    SELECT DISTINCT jsonb_extract_path_text(metadata, 'event_id')::text
                    FROM node_observations
                    WHERE metadata ? 'event_id'
                    UNION
                    SELECT DISTINCT jsonb_extract_path_text(metadata, 'event_id')::text
                    FROM trace_events
                    WHERE metadata ? 'event_id'
                )
                ORDER BY received_at
                LIMIT $1
                """,
                batch_size
            )

            processed = 0
            for row in rows:
                try:
                    event_type = row['event_type']

                    if event_type == 'packet':
                        await self.process_packet_event(
                            row['event_id'], row['collector_id'],
                            row['observed_at'], row['payload']
                        )
                    elif event_type == 'trace_event':
                        await self.process_trace_event(
                            row['event_id'], row['collector_id'],
                            row['observed_at'], row['payload']
                        )
                    elif event_type == 'collector_stats':
                        await self.process_collector_stats(
                            row['event_id'], row['collector_id'],
                            row['observed_at'], row['payload']
                        )

                    processed += 1

                except Exception as e:
                    logger.error(f"Error processing event {row['event_id']}: {e}", exc_info=True)

            return processed

    async def run_once(self, batch_size: int = 1000):
        """Run one processing cycle."""
        logger.info("Starting processing cycle...")
        processed = await self.process_batch(batch_size)
        logger.info(f"Processed {processed} events")
        return processed

    async def run_continuous(self, interval: int = 60, batch_size: int = 1000):
        """
        Run continuous processing loop.

        Args:
            interval: Seconds between processing cycles
            batch_size: Events per batch
        """
        logger.info(f"Starting continuous processing (interval: {interval}s, batch: {batch_size})")

        while True:
            try:
                processed = await self.process_batch(batch_size)
                if processed > 0:
                    logger.info(f"Processed {processed} events")
                else:
                    logger.debug("No events to process")

                await asyncio.sleep(interval)

            except KeyboardInterrupt:
                logger.info("Shutdown requested")
                break
            except Exception as e:
                logger.error(f"Error in processing loop: {e}", exc_info=True)
                await asyncio.sleep(interval)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Data processor for federated Meshtastic')
    parser.add_argument('--database-url', help='PostgreSQL connection URL (or use DATABASE_URL env var)')
    parser.add_argument('--batch-size', type=int, default=1000, help='Events per batch')
    parser.add_argument('--interval', type=int, default=60, help='Processing interval in seconds')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    database_url = args.database_url or os.environ.get('DATABASE_URL')
    if not database_url:
        logger.error("No database URL provided. Use --database-url or set DATABASE_URL")
        sys.exit(1)

    processor = DataProcessor(database_url)
    await processor.connect()

    try:
        if args.once:
            await processor.run_once(args.batch_size)
        else:
            await processor.run_continuous(args.interval, args.batch_size)
    finally:
        await processor.close()


if __name__ == '__main__':
    asyncio.run(main())
