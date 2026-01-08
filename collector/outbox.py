"""
Outbox database operations for the federated Meshtastic collector.
Implements the outbox pattern for reliable data uploads.
"""

import sqlite3
import hashlib
import json
import time
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path


class OutboxManager:
    """Manages the outbox table for reliable event uploads."""

    def __init__(self, db_path: str, collector_id: str):
        """
        Initialize the outbox manager.

        Args:
            db_path: Path to the SQLite database
            collector_id: Unique identifier for this collector
        """
        self.db_path = db_path
        self.collector_id = collector_id
        self._ensure_schema()

    def _ensure_schema(self):
        """Ensure the outbox table exists."""
        schema_path = Path(__file__).parent / "schema.sql"
        with sqlite3.connect(self.db_path) as conn:
            with open(schema_path, 'r') as f:
                conn.executescript(f.read())
            conn.commit()

    def _generate_event_id(self, event_data: Dict[str, Any]) -> str:
        """
        Generate a deterministic event ID for deduplication.

        The event ID is a SHA256 hash of:
        - collector_id
        - meshtastic_packet_id (if available)
        - timestamp
        - source_node_id (if available)

        Args:
            event_data: The event payload

        Returns:
            SHA256 hash as hex string
        """
        components = [
            self.collector_id,
            str(event_data.get('packet_id', '')),
            str(event_data.get('timestamp', time.time())),
            str(event_data.get('from_node', '')),
            str(event_data.get('to_node', '')),
        ]
        combined = '|'.join(components)
        return hashlib.sha256(combined.encode('utf-8')).hexdigest()

    def enqueue(self, event_type: str, payload: Dict[str, Any]) -> Optional[str]:
        """
        Add an event to the outbox for upload.

        Args:
            event_type: Type of event (packet, node_observation, trace_event)
            payload: Event data

        Returns:
            Event ID if successfully enqueued, None if duplicate
        """
        event_id = self._generate_event_id(payload)
        payload_json = json.dumps(payload)
        created_at = int(time.time())

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO outbox (event_id, collector_id, event_type, created_at, payload_json, next_attempt)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (event_id, self.collector_id, event_type, created_at, payload_json, created_at)
                )
                conn.commit()
            return event_id
        except sqlite3.IntegrityError:
            # Duplicate event_id, already enqueued
            return None

    def fetch_unsent(self, batch_size: int = 500) -> List[sqlite3.Row]:
        """
        Fetch unsent events that are ready for upload.

        Args:
            batch_size: Maximum number of events to fetch

        Returns:
            List of unsent event rows
        """
        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                """
                SELECT id, event_id, event_type, created_at, payload_json, attempts
                FROM outbox
                WHERE sent_at IS NULL AND next_attempt <= ?
                ORDER BY id
                LIMIT ?
                """,
                (now, batch_size)
            )
            return cur.fetchall()

    def mark_sent(self, event_ids: List[int]) -> int:
        """
        Mark events as successfully sent.

        Args:
            event_ids: List of outbox row IDs to mark as sent

        Returns:
            Number of rows updated
        """
        if not event_ids:
            return 0

        now = int(time.time())
        with sqlite3.connect(self.db_path) as conn:
            placeholders = ','.join('?' * len(event_ids))
            result = conn.execute(
                f"UPDATE outbox SET sent_at=? WHERE id IN ({placeholders})",
                [now] + event_ids
            )
            conn.commit()
            return result.rowcount

    def mark_failed(self, rows: List[sqlite3.Row],
                   min_retry_seconds: int = 5,
                   max_retry_seconds: int = 300) -> int:
        """
        Mark events as failed and schedule retry with exponential backoff.

        Args:
            rows: List of event rows that failed to upload
            min_retry_seconds: Minimum retry delay
            max_retry_seconds: Maximum retry delay

        Returns:
            Number of rows updated
        """
        if not rows:
            return 0

        now = int(time.time())
        updates = []

        for row in rows:
            attempts = row['attempts'] + 1
            # Exponential backoff: 2^attempts, capped at max_retry_seconds
            delay = min(max_retry_seconds, max(min_retry_seconds, 2 ** min(attempts, 8)))
            updates.append((attempts, now + delay, row['id']))

        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                "UPDATE outbox SET attempts=?, next_attempt=? WHERE id=?",
                updates
            )
            conn.commit()
            return len(updates)

    def get_stats(self) -> Dict[str, Any]:
        """
        Get outbox statistics.

        Returns:
            Dictionary with outbox stats
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            total = conn.execute("SELECT COUNT(*) as cnt FROM outbox").fetchone()['cnt']
            sent = conn.execute("SELECT COUNT(*) as cnt FROM outbox WHERE sent_at IS NOT NULL").fetchone()['cnt']
            pending = conn.execute("SELECT COUNT(*) as cnt FROM outbox WHERE sent_at IS NULL").fetchone()['cnt']
            failed = conn.execute(
                "SELECT COUNT(*) as cnt FROM outbox WHERE sent_at IS NULL AND attempts > 0"
            ).fetchone()['cnt']

            return {
                'total': total,
                'sent': sent,
                'pending': pending,
                'failed': failed,
                'success_rate': round(sent / total * 100, 2) if total > 0 else 0
            }

    def cleanup_old_sent(self, days: int = 7) -> int:
        """
        Remove old sent events to prevent database bloat.

        Args:
            days: Remove events sent more than this many days ago

        Returns:
            Number of rows deleted
        """
        cutoff = int(time.time()) - (days * 86400)
        with sqlite3.connect(self.db_path) as conn:
            result = conn.execute(
                "DELETE FROM outbox WHERE sent_at IS NOT NULL AND sent_at < ?",
                (cutoff,)
            )
            conn.commit()
            return result.rowcount
