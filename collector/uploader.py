#!/usr/bin/env python3
"""
Collector uploader service for federated Meshtastic system.
Continuously uploads events from the outbox to the central API.
"""

import json
import gzip
import time
import logging
import argparse
import os
import sys
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import sqlite3

import requests

from outbox import OutboxManager


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CollectorUploader:
    """Handles uploading events from the outbox to the central API."""

    def __init__(
        self,
        api_url: str,
        collector_id: str,
        token: str,
        db_path: str = "collector.sqlite",
        batch_size: int = 500,
        min_retry_seconds: int = 5,
        max_retry_seconds: int = 300,
        poll_interval: int = 5
    ):
        """
        Initialize the uploader.

        Args:
            api_url: Base URL of the central API
            collector_id: Unique identifier for this collector
            token: Authentication token
            db_path: Path to SQLite database
            batch_size: Number of events per batch
            min_retry_seconds: Minimum retry delay
            max_retry_seconds: Maximum retry delay
            poll_interval: Seconds to wait between polls when queue is empty
        """
        self.api_url = api_url.rstrip('/') + '/v1/ingest/batch'
        self.collector_id = collector_id
        self.token = token
        self.batch_size = batch_size
        self.min_retry_seconds = min_retry_seconds
        self.max_retry_seconds = max_retry_seconds
        self.poll_interval = poll_interval

        self.outbox = OutboxManager(db_path, collector_id)
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        })

    def utc_iso(self, ts: int) -> str:
        """Convert unix timestamp to ISO 8601 UTC string."""
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace('+00:00', 'Z')

    def post_batch(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Post a batch of events to the central API.

        Args:
            events: List of events to upload

        Returns:
            API response as dictionary

        Raises:
            requests.RequestException: If the request fails
        """
        body = {
            'schema_version': 1,
            'collector_id': self.collector_id,
            'sent_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'events': events
        }

        # Compress the payload
        raw = json.dumps(body).encode('utf-8')
        compressed = gzip.compress(raw)

        logger.info(f"Uploading batch of {len(events)} events ({len(raw)} bytes, {len(compressed)} compressed)")

        headers = {'Content-Encoding': 'gzip'}
        resp = self.session.post(
            self.api_url,
            data=compressed,
            headers=headers,
            timeout=30
        )
        resp.raise_for_status()

        return resp.json()

    def process_batch(self) -> bool:
        """
        Process one batch of unsent events.

        Returns:
            True if a batch was processed, False if queue was empty
        """
        rows = self.outbox.fetch_unsent(self.batch_size)
        if not rows:
            return False

        # Build event list
        events = []
        row_map = {}  # Maps event_id to row

        for r in rows:
            event_id = r['event_id']
            row_map[event_id] = r

            events.append({
                'event_id': event_id,
                'event_type': r['event_type'],
                'observed_at': self.utc_iso(r['created_at']),
                'payload': json.loads(r['payload_json'])
            })

        # Upload batch
        try:
            response = self.post_batch(events)
            accepted = set(response.get('accepted', []))
            rejected = response.get('rejected', [])

            # Mark accepted events as sent
            sent_ids = [row_map[event_id]['id'] for event_id in accepted if event_id in row_map]
            if sent_ids:
                count = self.outbox.mark_sent(sent_ids)
                logger.info(f"Marked {count} events as sent")

            # Mark rejected events as failed
            rejected_event_ids = [r['event_id'] for r in rejected]
            rejected_rows = [row_map[event_id] for event_id in rejected_event_ids if event_id in row_map]
            if rejected_rows:
                count = self.outbox.mark_failed(rejected_rows, self.min_retry_seconds, self.max_retry_seconds)
                logger.warning(f"Marked {count} events as failed: {rejected}")

            return True

        except requests.RequestException as e:
            logger.error(f"Upload failed: {e}")
            # Mark all events in batch as failed for retry
            count = self.outbox.mark_failed(list(rows), self.min_retry_seconds, self.max_retry_seconds)
            logger.info(f"Marked {count} events for retry")
            return True

        except Exception as e:
            logger.error(f"Unexpected error processing batch: {e}", exc_info=True)
            # Mark all events in batch as failed for retry
            count = self.outbox.mark_failed(list(rows), self.min_retry_seconds, self.max_retry_seconds)
            logger.info(f"Marked {count} events for retry")
            return True

    def run(self):
        """Main run loop."""
        logger.info(f"Starting uploader for collector '{self.collector_id}'")
        logger.info(f"API URL: {self.api_url}")

        while True:
            try:
                # Process batches until queue is empty
                while self.process_batch():
                    # Log stats periodically
                    stats = self.outbox.get_stats()
                    logger.info(f"Outbox stats: {stats}")

                # Queue is empty, wait before polling again
                logger.debug(f"Queue empty, sleeping for {self.poll_interval}s")
                time.sleep(self.poll_interval)

            except KeyboardInterrupt:
                logger.info("Shutdown requested")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
                time.sleep(self.poll_interval)

        logger.info("Uploader stopped")

    def cleanup_old_sent(self, days: int = 7):
        """Clean up old sent events."""
        count = self.outbox.cleanup_old_sent(days)
        logger.info(f"Cleaned up {count} old sent events (older than {days} days)")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Collector uploader for federated Meshtastic')
    parser.add_argument('--api-url', required=True, help='Central API URL')
    parser.add_argument('--collector-id', required=True, help='Collector identifier')
    parser.add_argument('--token', help='Authentication token (or use COLLECTOR_TOKEN env var)')
    parser.add_argument('--db-path', default='collector.sqlite', help='SQLite database path')
    parser.add_argument('--batch-size', type=int, default=500, help='Events per batch')
    parser.add_argument('--poll-interval', type=int, default=5, help='Poll interval in seconds')
    parser.add_argument('--cleanup-days', type=int, help='Clean up sent events older than N days')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Get token from args or environment
    token = args.token or os.environ.get('COLLECTOR_TOKEN')
    if not token:
        logger.error("No token provided. Use --token or set COLLECTOR_TOKEN environment variable")
        sys.exit(1)

    uploader = CollectorUploader(
        api_url=args.api_url,
        collector_id=args.collector_id,
        token=token,
        db_path=args.db_path,
        batch_size=args.batch_size,
        poll_interval=args.poll_interval
    )

    # Run cleanup if requested
    if args.cleanup_days:
        uploader.cleanup_old_sent(args.cleanup_days)
        return

    # Run main loop
    uploader.run()


if __name__ == '__main__':
    main()
