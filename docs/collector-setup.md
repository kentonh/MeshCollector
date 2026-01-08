# Collector Setup Guide

This guide walks you through setting up a Meshtastic collector on a Raspberry Pi or similar Linux device.

## Prerequisites

- Raspberry Pi 3/4 or similar Linux device
- Python 3.9 or higher
- Meshtastic node connected via USB or network
- Internet connection
- SQLite 3

## Installation

### 1. Install System Dependencies

```bash
sudo apt-get update
sudo apt-get install python3 python3-pip sqlite3
```

### 2. Download Collector Code

```bash
mkdir -p ~/meshtastic-collector
cd ~/meshtastic-collector

# Copy the collector files:
# - outbox.py
# - uploader.py
# - schema.sql
# - requirements.txt
```

### 3. Install Python Dependencies

```bash
pip3 install -r requirements.txt
```

### 4. Initialize Database

The database will be automatically initialized when you first run the outbox or uploader, but you can verify the schema:

```bash
sqlite3 collector.sqlite < schema.sql
```

## Configuration

### 1. Get Your Collector Token

Contact your system administrator or generate a secure token:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Save this token - you'll need it for both the collector and the central API.

### 2. Test the Uploader

Before setting up as a service, test the uploader manually:

```bash
python3 uploader.py \
  --api-url https://your-app.fly.dev \
  --collector-id your-collector-01 \
  --token YOUR_TOKEN_HERE \
  --db-path collector.sqlite \
  --batch-size 500 \
  --poll-interval 5
```

You should see log output indicating connection to the API.

## Integration with Your Meshtastic Collector

The outbox system needs to be integrated with your existing Meshtastic packet collection code.

### Example Integration

```python
from outbox import OutboxManager

# Initialize outbox
outbox = OutboxManager('collector.sqlite', 'your-collector-01')

# When you receive a packet from Meshtastic:
def on_packet_received(packet):
    # Create event payload
    event_data = {
        'packet_id': packet.id,
        'from_node': packet.from_node,
        'to_node': packet.to_node,
        'timestamp': time.time(),
        'rssi': packet.rssi,
        'snr': packet.snr,
        'relay_node': packet.via_mqtt,  # if relayed
        'port_num': packet.decoded.portnum,
        'channel': packet.channel,
        'hop_limit': packet.hop_limit,
        'hop_start': packet.hop_start,
        # Add any other relevant fields
    }

    # Enqueue for upload
    event_id = outbox.enqueue('packet', event_data)
    if event_id:
        print(f"Enqueued packet {packet.id} as event {event_id}")
```

## Running as a Service

### 1. Create systemd Service

Copy the service file to systemd:

```bash
sudo cp meshtastic-uploader.service /etc/systemd/system/
```

### 2. Edit Service Configuration

Edit the service file to match your setup:

```bash
sudo nano /etc/systemd/system/meshtastic-uploader.service
```

Update these fields:
- `User` and `Group` - Your username (usually `pi`)
- `WorkingDirectory` - Path to your collector directory
- `Environment="COLLECTOR_TOKEN=..."` - Your collector token
- `--api-url` - Your central API URL
- `--collector-id` - Your collector identifier
- `--db-path` - Path to your SQLite database

### 3. Enable and Start Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable meshtastic-uploader

# Start service
sudo systemctl start meshtastic-uploader

# Check status
sudo systemctl status meshtastic-uploader
```

### 4. View Logs

```bash
# Follow logs in real-time
sudo journalctl -u meshtastic-uploader -f

# View recent logs
sudo journalctl -u meshtastic-uploader -n 100
```

## Maintenance

### Check Outbox Status

```python
from outbox import OutboxManager

outbox = OutboxManager('collector.sqlite', 'your-collector-01')
stats = outbox.get_stats()
print(stats)
# Output: {'total': 1500, 'sent': 1450, 'pending': 45, 'failed': 5, 'success_rate': 96.67}
```

### Clean Up Old Events

The uploader has a built-in cleanup command:

```bash
python3 uploader.py \
  --api-url https://your-app.fly.dev \
  --collector-id your-collector-01 \
  --token YOUR_TOKEN_HERE \
  --cleanup-days 7
```

This removes events successfully sent more than 7 days ago.

### Restart Service

```bash
sudo systemctl restart meshtastic-uploader
```

### Stop Service

```bash
sudo systemctl stop meshtastic-uploader
```

## Troubleshooting

### Uploader Won't Start

Check the logs:
```bash
sudo journalctl -u meshtastic-uploader -n 50
```

Common issues:
- **"No token provided"** - Set COLLECTOR_TOKEN in service file
- **"Connection refused"** - Check API URL and network connectivity
- **"401 Unauthorized"** - Token mismatch with central API

### Database Lock Errors

If you see "database is locked" errors, make sure:
- Only one uploader process is running
- Your packet collector isn't holding long transactions
- The database file has proper permissions

```bash
chmod 664 collector.sqlite
```

### High Memory Usage

If the outbox grows too large, clean up old sent events:

```bash
python3 uploader.py --cleanup-days 1
```

Also check for failed events piling up:

```sql
sqlite3 collector.sqlite "SELECT COUNT(*) FROM outbox WHERE sent_at IS NULL AND attempts > 5;"
```

### Network Issues

The uploader has built-in retry with exponential backoff. If you have persistent network issues:

1. Check API endpoint is accessible:
```bash
curl https://your-app.fly.dev/health
```

2. Adjust retry settings in uploader.py if needed

3. Consider increasing poll interval during network maintenance

## Performance Tuning

### Batch Size

Adjust `--batch-size` based on your packet volume:
- Low volume (< 100/hour): 100-200
- Medium volume (100-1000/hour): 500-1000
- High volume (> 1000/hour): 1000-2000

### Poll Interval

Adjust `--poll-interval` based on latency requirements:
- Real-time (5s poll)
- Normal (30s poll)
- Low bandwidth (60s+ poll)

## Security

### Token Storage

Never commit tokens to git. Use environment variables:

```bash
echo "export COLLECTOR_TOKEN='your-token-here'" >> ~/.bashrc
source ~/.bashrc
```

### Database Permissions

Ensure only your user can read the database:

```bash
chmod 600 collector.sqlite
```

### Firewall

The collector only needs outbound HTTPS (port 443):

```bash
sudo ufw allow out 443/tcp
```

## Next Steps

- [API Deployment Guide](api-deployment.md) - Set up the central API
- [Integration Guide](integration.md) - Integrate with your Meshtastic code
- [Jekyll Deployment Guide](jekyll-deployment.md) - Deploy the web interface
