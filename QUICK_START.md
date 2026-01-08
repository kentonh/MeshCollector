# Quick Start Guide

Get your federated Meshtastic system running in 30 minutes.

## Prerequisites

- Fly.io account (free tier works)
- GitHub account
- Raspberry Pi with Meshtastic node
- Python 3.9+ on collector
- 30 minutes

## Step 1: Deploy Central API (5 min)

```bash
cd federated-meshtastic/api

# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Login
flyctl auth login

# Create PostgreSQL
flyctl postgres create --name meshtastic-db --region ord

# Note the DATABASE_URL from output
# Should look like: postgres://user:pass@meshtastic-db.internal:5432/db

# Launch API
flyctl launch --no-deploy

# Set secrets
flyctl secrets set DATABASE_URL="<your-postgres-url>"
flyctl secrets set COLLECTOR_TOKEN_COLLECTOR1="<generate-random-token>"

# Deploy
flyctl deploy

# Test
curl https://your-app.fly.dev/health
```

**Generate a secure token:**
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Save this token - you'll need it for the collector!

---

## Step 2: Set Up Collector (10 min)

On your Raspberry Pi:

```bash
# Install dependencies
sudo apt-get update
sudo apt-get install python3 python3-pip

# Create directory
mkdir ~/meshtastic-collector
cd ~/meshtastic-collector

# Copy collector files from repo:
# - outbox.py
# - uploader.py
# - schema.sql
# - requirements.txt

# Install Python packages
pip3 install -r requirements.txt

# Test uploader (replace with your values)
python3 uploader.py \
  --api-url https://your-app.fly.dev \
  --collector-id collector-01 \
  --token <your-token-from-step-1> \
  --db-path collector.sqlite \
  --debug
```

Should see: "Starting uploader for collector 'collector-01'"

**Press Ctrl+C** to stop after verifying connection.

---

## Step 3: Integrate with Your Packet Collector (5 min)

Add to your existing Meshtastic collector code:

```python
from outbox import OutboxManager

# Initialize outbox
outbox = OutboxManager('collector.sqlite', 'collector-01')

# When you receive a packet:
def on_packet_received(packet):
    event_data = {
        'packet_id': packet.id,
        'from_node': f"!{packet.from:08x}",
        'to_node': f"!{packet.to:08x}",
        'timestamp': time.time(),
        'rssi': packet.rx_rssi,
        'snr': packet.rx_snr,
        # Add more fields as needed
    }

    event_id = outbox.enqueue('packet', event_data)
    if event_id:
        print(f"Enqueued packet {packet.id}")
```

See [Integration Guide](docs/integration.md) for complete examples.

---

## Step 4: Run Uploader as Service (5 min)

```bash
# Copy service file
sudo cp meshtastic-uploader.service /etc/systemd/system/

# Edit service file
sudo nano /etc/systemd/system/meshtastic-uploader.service

# Update these lines:
# - User=pi (your username)
# - WorkingDirectory=/home/pi/meshtastic-collector
# - Environment="COLLECTOR_TOKEN=<your-token>"
# - --api-url https://your-app.fly.dev
# - --collector-id collector-01

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable meshtastic-uploader
sudo systemctl start meshtastic-uploader

# Check status
sudo systemctl status meshtastic-uploader

# View logs
sudo journalctl -u meshtastic-uploader -f
```

---

## Step 5: Deploy Website (5 min)

```bash
cd federated-meshtastic/jekyll-site

# Edit _config.yml
nano _config.yml

# Update these lines:
api_url: "https://your-app.fly.dev"
url: "https://yourusername.github.io"

# Initialize git
git init
git add .
git commit -m "Initial site"

# Create GitHub repo named "meshtastic-explorer"
# Then push:
git remote add origin https://github.com/yourusername/meshtastic-explorer.git
git branch -M main
git push -u origin main

# Enable GitHub Pages:
# Go to repo settings → Pages → Select "main" branch → Save
```

Your site will be live at: `https://yourusername.github.io/meshtastic-explorer`

**Update baseurl in _config.yml**:
```yaml
baseurl: "/meshtastic-explorer"
```

Commit and push again.

---

## Step 6: Verify Everything Works

### Check Collector
```bash
# On Raspberry Pi
sudo journalctl -u meshtastic-uploader -n 50

# Should see:
# "Received batch from 'collector-01' with X events"
# "Processed X events"
```

### Check API
```bash
# From anywhere
curl https://your-app.fly.dev/v1/stats

# Should return JSON with node/packet counts
```

### Check Website
1. Visit: `https://yourusername.github.io/meshtastic-explorer`
2. Should see dashboard with statistics
3. Click "Nodes" → Should see node list
4. Click "Map" → Should see nodes on map

---

## Troubleshooting

### Collector Not Uploading

```bash
# Check service status
sudo systemctl status meshtastic-uploader

# Check logs
sudo journalctl -u meshtastic-uploader -n 100

# Common issues:
# - "401 Unauthorized" → Token mismatch
# - "Connection refused" → Wrong API URL
# - "No token provided" → Missing COLLECTOR_TOKEN in service file
```

### API Errors

```bash
# Check API logs
flyctl logs -a your-app-name

# Check health
curl https://your-app.fly.dev/health

# Verify database
flyctl postgres connect -a meshtastic-db
```

### Website Not Loading Data

1. Open browser console (F12)
2. Check for errors
3. Verify API URL in `_config.yml`
4. Ensure API returns data: `curl https://your-app.fly.dev/v1/stats`
5. Check CORS in API (should allow your GitHub Pages domain)

---

## Next Steps

### Add More Collectors

1. Generate new token:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. Add to API:
   ```bash
   flyctl secrets set COLLECTOR_TOKEN_COLLECTOR2="<new-token>"
   ```

3. Set up new Raspberry Pi with uploader (Step 2-4)

### Customize Website

- Edit colors in `assets/css/main.css`
- Add logo to `assets/images/`
- Update map center in `_config.yml`
- Add custom pages

### Monitor Performance

```bash
# API metrics
flyctl metrics -a your-app-name

# Database size
flyctl postgres connect -a meshtastic-db
# Then: SELECT pg_size_pretty(pg_database_size('database_name'));

# Collector stats
python3 -c "from outbox import OutboxManager; print(OutboxManager('collector.sqlite', 'collector-01').get_stats())"
```

---

## Cost Estimate

### Minimal Setup (1 collector)
- **Fly.io**: ~$5-10/month (shared CPU + 10GB PostgreSQL)
- **GitHub Pages**: Free
- **Collector**: Just electricity for Raspberry Pi

### Production Setup (3 collectors)
- **Fly.io**: ~$20-30/month (dedicated CPU + 20GB PostgreSQL)
- **GitHub Pages**: Free (or custom domain ~$12/year)
- **Collectors**: 3× Raspberry Pi electricity

---

## Getting Help

### Documentation
- [Main README](README.md) - Full documentation
- [Collector Setup](docs/collector-setup.md) - Detailed collector guide
- [API Deployment](docs/api-deployment.md) - API deployment details
- [Jekyll Deployment](docs/jekyll-deployment.md) - Website deployment
- [Integration Guide](docs/integration.md) - Code integration examples

### Community
- [Meshtastic Discord](https://discord.gg/meshtastic)
- [Meshtastic Forums](https://meshtastic.discourse.group)

### Issues
Report bugs or request features:
- GitHub Issues (your repo)

---

## Success Checklist

- [ ] API deployed and healthy (`/health` returns 200)
- [ ] PostgreSQL database connected
- [ ] Collector token configured
- [ ] Uploader service running on Raspberry Pi
- [ ] Packets being enqueued to outbox
- [ ] Events uploading to API (check logs)
- [ ] API receiving events (check `/v1/stats`)
- [ ] Website deployed to GitHub Pages
- [ ] Website loading data from API
- [ ] Map showing nodes
- [ ] Dashboard showing statistics

---

**Congratulations!** 🎉

Your federated Meshtastic network is now live!

- Collectors reliably upload data
- Central API aggregates everything
- Public website visualizes the network
- All components auto-recover from failures

**Enjoy exploring your mesh network!**
