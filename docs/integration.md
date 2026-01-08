# Integration Guide

This guide shows how to integrate the federated Meshtastic system with your existing packet collector code.

## Overview

The integration involves:
1. Using `OutboxManager` to enqueue events
2. Running the `uploader.py` service to upload events
3. Structuring event payloads correctly

## Basic Integration

### 1. Import OutboxManager

```python
from outbox import OutboxManager

# Initialize with your database path and collector ID
outbox = OutboxManager(
    db_path='collector.sqlite',
    collector_id='my-collector-01'
)
```

### 2. Enqueue Events

When you capture a Meshtastic packet:

```python
def on_packet_received(packet):
    """Called when a packet is received from Meshtastic."""

    # Build event payload
    event_data = {
        'packet_id': packet.id,
        'from_node': hex(packet.from_node),
        'to_node': hex(packet.to_node),
        'timestamp': time.time(),
        'rssi': packet.rx_rssi if hasattr(packet, 'rx_rssi') else None,
        'snr': packet.rx_snr if hasattr(packet, 'rx_snr') else None,
        'channel': packet.channel,
        'hop_limit': packet.hop_limit,
        'hop_start': packet.hop_start,
    }

    # Add node info if available
    if hasattr(packet, 'from_node_info'):
        event_data['from_node_info'] = {
            'short_name': packet.from_node_info.user.short_name,
            'long_name': packet.from_node_info.user.long_name,
            'hardware': packet.from_node_info.user.hw_model_string,
            'role': packet.from_node_info.user.role_string,
        }

    # Add position if available
    if hasattr(packet, 'decoded') and packet.decoded.portnum == 'POSITION_APP':
        position = packet.decoded.position
        event_data['from_node_info']['latitude'] = position.latitude_i / 1e7
        event_data['from_node_info']['longitude'] = position.longitude_i / 1e7
        event_data['from_node_info']['altitude'] = position.altitude

    # Enqueue for upload
    event_id = outbox.enqueue('packet', event_data)
    if event_id:
        logger.info(f"Enqueued packet {packet.id}")
    else:
        logger.debug(f"Duplicate packet {packet.id}")
```

## Event Schema Reference

### Packet Events

```python
{
    'packet_id': int,              # Required: Packet identifier
    'from_node': str,              # Required: Source node ID (hex)
    'to_node': str,                # Required: Destination node ID (hex)
    'timestamp': float,            # Required: Unix timestamp
    'rssi': int | None,            # Optional: Signal strength (dBm)
    'snr': float | None,           # Optional: Signal-to-noise ratio (dB)
    'channel': int | None,         # Optional: Channel index
    'port_num': str | None,        # Optional: Port name (e.g., 'TEXT_MESSAGE_APP')
    'hop_limit': int | None,       # Optional: Remaining hops
    'hop_start': int | None,       # Optional: Initial hop count
    'relay_node': str | None,      # Optional: Node that relayed this packet

    # Optional: Source node metadata
    'from_node_info': {
        'short_name': str,
        'long_name': str,
        'hardware': str,
        'role': str,
        'latitude': float,         # Decimal degrees
        'longitude': float,        # Decimal degrees
        'altitude': int,           # Meters
        'battery_level': int,      # Percentage (0-100)
    },

    # Optional: Destination node metadata
    'to_node_info': {
        # Same structure as from_node_info
    },

    # Optional: Additional data
    'type': str,                   # Payload type
    'payload': dict,               # Decoded payload
}
```

### Trace Events

For explicit traceroute data:

```python
{
    'trace_id': str,               # Required: Unique trace identifier
    'source_node': str,            # Required: Trace source
    'dest_node': str,              # Required: Trace destination
    'timestamp': float,            # Required: Unix timestamp
    'hops': [                      # Required: List of hops
        {
            'node_id': str,        # Node at this hop
            'rssi': int | None,    # Signal strength
            'snr': float | None,   # Signal quality
            'timestamp': float,    # When this hop occurred
        }
    ]
}
```

### Collector Stats Events

For health monitoring:

```python
{
    'timestamp': float,            # Required: Unix timestamp
    'packets_rx': int,             # Packets received since start
    'unique_nodes': int,           # Unique nodes seen
    'uptime_seconds': int,         # Collector uptime
    'version': str,                # Software version
    'metadata': {                  # Optional additional stats
        'cpu_usage': float,
        'memory_usage': float,
        'disk_usage': float,
    }
}
```

## Complete Example

### Python Collector with Meshtastic Library

```python
#!/usr/bin/env python3
"""
Meshtastic collector with federated upload support.
"""

import time
import logging
from pubsub import pub
from meshtastic.serial_interface import SerialInterface
from outbox import OutboxManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize outbox
outbox = OutboxManager('collector.sqlite', 'my-collector-01')

def on_receive(packet, interface):
    """Callback when packet is received."""
    try:
        # Extract basic packet info
        event_data = {
            'packet_id': packet.get('id', 0),
            'from_node': f"!{packet['from']:08x}",
            'to_node': f"!{packet['to']:08x}",
            'timestamp': time.time(),
            'channel': packet.get('channel', 0),
            'hop_limit': packet.get('hopLimit'),
            'hop_start': packet.get('hopStart'),
        }

        # Add RX metadata
        if 'rxRssi' in packet:
            event_data['rssi'] = packet['rxRssi']
        if 'rxSnr' in packet:
            event_data['snr'] = packet['rxSnr']

        # Add relay information if present
        if 'viaMqtt' in packet and packet['viaMqtt']:
            event_data['relay_node'] = f"!{packet.get('fromId', 0):08x}"

        # Handle decoded data
        if 'decoded' in packet:
            decoded = packet['decoded']
            portnum = decoded.get('portnum', '')

            event_data['port_num'] = portnum
            event_data['type'] = portnum

            # Extract position
            if portnum == 'POSITION_APP' and 'position' in decoded:
                pos = decoded['position']
                event_data['from_node_info'] = {
                    'latitude': pos.get('latitude'),
                    'longitude': pos.get('longitude'),
                    'altitude': pos.get('altitude'),
                }

            # Extract node info
            if portnum == 'NODEINFO_APP' and 'user' in decoded:
                user = decoded['user']
                event_data['from_node_info'] = event_data.get('from_node_info', {})
                event_data['from_node_info'].update({
                    'short_name': user.get('shortName'),
                    'long_name': user.get('longName'),
                    'hardware': user.get('hwModel'),
                    'role': user.get('role'),
                })

            # Extract telemetry
            if portnum == 'TELEMETRY_APP' and 'telemetry' in decoded:
                telem = decoded['telemetry']
                if 'deviceMetrics' in telem:
                    metrics = telem['deviceMetrics']
                    event_data['from_node_info'] = event_data.get('from_node_info', {})
                    event_data['from_node_info']['battery_level'] = metrics.get('batteryLevel')

        # Enqueue event
        event_id = outbox.enqueue('packet', event_data)
        if event_id:
            logger.info(f"Enqueued packet from {event_data['from_node']}")

    except Exception as e:
        logger.error(f"Error processing packet: {e}", exc_info=True)

def on_connection(interface, topic=pub.AUTO_TOPIC):
    """Callback when connection is established."""
    logger.info("Connected to Meshtastic device")

def main():
    """Main entry point."""
    logger.info("Starting Meshtastic collector")

    # Subscribe to packet events
    pub.subscribe(on_receive, "meshtastic.receive")
    pub.subscribe(on_connection, "meshtastic.connection.established")

    # Connect to Meshtastic device
    try:
        interface = SerialInterface()
        logger.info("Listening for packets...")

        # Periodically log stats
        while True:
            time.sleep(300)  # Every 5 minutes
            stats = outbox.get_stats()
            logger.info(f"Outbox stats: {stats}")

            # Enqueue collector stats
            outbox.enqueue('collector_stats', {
                'timestamp': time.time(),
                'packets_rx': stats['total'],
                'unique_nodes': 0,  # Could track this
                'uptime_seconds': int(time.time() - start_time),
                'version': '1.0.0',
            })

    except KeyboardInterrupt:
        logger.info("Shutting down")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)

if __name__ == '__main__':
    start_time = time.time()
    main()
```

### Running the Complete System

1. **Start your collector**:
```bash
python3 my_collector.py
```

2. **Start the uploader** (separate process):
```bash
python3 uploader.py \
  --api-url https://your-api.fly.dev \
  --collector-id my-collector-01 \
  --token YOUR_TOKEN \
  --db-path collector.sqlite
```

Or use systemd (recommended for production).

## Advanced Integration

### Custom Event Processing

Add processing before enqueueing:

```python
from outbox import OutboxManager

class EnhancedOutbox:
    def __init__(self, db_path, collector_id):
        self.outbox = OutboxManager(db_path, collector_id)
        self.node_cache = {}

    def enqueue_packet(self, packet):
        """Enqueue packet with enrichment."""
        event_data = self._build_event_data(packet)

        # Enrich with cached node info
        from_node = event_data['from_node']
        if from_node in self.node_cache:
            event_data['from_node_info'] = self.node_cache[from_node]

        # Privacy: round coordinates
        if 'from_node_info' in event_data:
            if 'latitude' in event_data['from_node_info']:
                event_data['from_node_info']['latitude'] = round(
                    event_data['from_node_info']['latitude'], 3
                )
            if 'longitude' in event_data['from_node_info']:
                event_data['from_node_info']['longitude'] = round(
                    event_data['from_node_info']['longitude'], 3
                )

        return self.outbox.enqueue('packet', event_data)

    def update_node_cache(self, node_id, node_info):
        """Update cached node information."""
        self.node_cache[node_id] = node_info
```

### Batch Processing

For high-volume collectors:

```python
import queue
import threading

class BatchedOutbox:
    def __init__(self, outbox_manager, batch_size=100):
        self.outbox = outbox_manager
        self.queue = queue.Queue()
        self.batch_size = batch_size
        self.running = False
        self.thread = None

    def start(self):
        """Start background thread."""
        self.running = True
        self.thread = threading.Thread(target=self._process_queue)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        """Stop background thread."""
        self.running = False
        if self.thread:
            self.thread.join()

    def enqueue(self, event_type, event_data):
        """Add event to queue."""
        self.queue.put((event_type, event_data))

    def _process_queue(self):
        """Process events in batches."""
        batch = []

        while self.running:
            try:
                # Get items from queue
                while len(batch) < self.batch_size:
                    try:
                        item = self.queue.get(timeout=1)
                        batch.append(item)
                    except queue.Empty:
                        break

                # Process batch
                if batch:
                    for event_type, event_data in batch:
                        self.outbox.enqueue(event_type, event_data)
                    batch.clear()

            except Exception as e:
                logger.error(f"Error processing batch: {e}")
```

## Testing

### Unit Tests

```python
import unittest
from outbox import OutboxManager
import tempfile
import os

class TestOutbox(unittest.TestCase):
    def setUp(self):
        self.db_file = tempfile.NamedTemporaryFile(delete=False)
        self.db_path = self.db_file.name
        self.outbox = OutboxManager(self.db_path, 'test-collector')

    def tearDown(self):
        os.unlink(self.db_path)

    def test_enqueue(self):
        """Test event enqueueing."""
        event_data = {
            'packet_id': 12345,
            'from_node': '!abcdef01',
            'to_node': '!12345678',
            'timestamp': time.time(),
        }

        event_id = self.outbox.enqueue('packet', event_data)
        self.assertIsNotNone(event_id)

        # Verify stats
        stats = self.outbox.get_stats()
        self.assertEqual(stats['total'], 1)
        self.assertEqual(stats['pending'], 1)

    def test_deduplication(self):
        """Test duplicate detection."""
        event_data = {
            'packet_id': 12345,
            'from_node': '!abcdef01',
            'to_node': '!12345678',
            'timestamp': time.time(),
        }

        event_id1 = self.outbox.enqueue('packet', event_data)
        event_id2 = self.outbox.enqueue('packet', event_data)

        self.assertIsNotNone(event_id1)
        self.assertIsNone(event_id2)  # Duplicate

if __name__ == '__main__':
    unittest.main()
```

### Integration Tests

Test the full flow:

```python
import asyncio
from unittest.mock import Mock, patch

async def test_full_flow():
    """Test collector → outbox → uploader → API."""

    # 1. Create test packet
    packet = {
        'id': 12345,
        'from': 0xabcdef01,
        'to': 0x12345678,
        'rxRssi': -85,
        'rxSnr': 5.5,
    }

    # 2. Process with collector
    outbox = OutboxManager('test.db', 'test-collector')
    on_receive(packet, None)

    # 3. Verify enqueued
    stats = outbox.get_stats()
    assert stats['pending'] > 0

    # 4. Mock API and test uploader
    with patch('requests.post') as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            'accepted': [event_id]
        }

        # Run uploader
        uploader = CollectorUploader(
            'http://test-api',
            'test-collector',
            'test-token',
            'test.db'
        )
        uploader.process_batch()

    # 5. Verify sent
    stats = outbox.get_stats()
    assert stats['sent'] > 0
```

## Monitoring

### Log Outbox Stats

```python
import logging
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()

def log_stats():
    """Log outbox statistics."""
    stats = outbox.get_stats()
    logger.info(f"Outbox: {stats['pending']} pending, "
                f"{stats['sent']} sent, "
                f"{stats['success_rate']}% success rate")

# Log stats every 5 minutes
scheduler.add_job(log_stats, 'interval', minutes=5)
scheduler.start()
```

### Alert on Failures

```python
def check_failures():
    """Alert if too many failures."""
    stats = outbox.get_stats()

    if stats['failed'] > 100:
        send_alert(f"Outbox has {stats['failed']} failed events")

    if stats['success_rate'] < 90:
        send_alert(f"Low success rate: {stats['success_rate']}%")
```

## Troubleshooting

### Events Not Uploading

Check:
1. Uploader service is running
2. API URL is correct
3. Token is valid
4. Network connectivity

Debug:
```python
# Check pending events
rows = outbox.fetch_unsent(10)
for row in rows:
    print(f"Event {row['event_id']}: {row['attempts']} attempts")
```

### Database Growing Too Large

Clean up old events:
```python
# Remove events older than 7 days
count = outbox.cleanup_old_sent(days=7)
print(f"Removed {count} old events")
```

Or via cron:
```bash
0 2 * * * python3 uploader.py --cleanup-days 7
```

## Next Steps

- [Collector Setup Guide](collector-setup.md) - Deploy collector
- [API Deployment Guide](api-deployment.md) - Deploy API
- [Jekyll Deployment Guide](jekyll-deployment.md) - Deploy website
