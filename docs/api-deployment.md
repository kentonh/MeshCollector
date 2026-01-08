# API Deployment Guide

This guide covers deploying the central FastAPI application to Fly.io with PostgreSQL.

## Prerequisites

- [Fly.io account](https://fly.io/app/sign-up)
- [Fly CLI installed](https://fly.io/docs/hands-on/install-flyctl/)
- Git installed
- Python 3.9+ (for local testing)

## Initial Setup

### 1. Install Fly CLI

```bash
# macOS
brew install flyctl

# Linux
curl -L https://fly.io/install.sh | sh

# Windows
pwsh -Command "iwr https://fly.io/install.ps1 -useb | iex"
```

### 2. Log In to Fly.io

```bash
flyctl auth login
```

### 3. Prepare API Code

```bash
cd api

# Verify files exist:
ls -la
# Should see: main.py, processor.py, schema.sql, requirements.txt, Dockerfile, fly.toml
```

## Deploy PostgreSQL Database

### 1. Create Postgres Cluster

```bash
flyctl postgres create \
  --name meshtastic-db \
  --region ord \
  --initial-cluster-size 1 \
  --vm-size shared-cpu-1x \
  --volume-size 10
```

Choose a region close to your collectors. Common regions:
- `ord` - Chicago
- `sea` - Seattle
- `iad` - Virginia
- `fra` - Frankfurt
- `syd` - Sydney

### 2. Note the Connection String

Fly will output a connection string like:
```
postgres://username:password@meshtastic-db.internal:5432/database_name
```

Save this - you'll need it later.

### 3. Verify Database

```bash
flyctl postgres connect -a meshtastic-db

# Inside psql:
\l  # List databases
\q  # Quit
```

## Deploy FastAPI Application

### 1. Initialize Fly App

```bash
flyctl launch --no-deploy
```

Answer the prompts:
- **App name**: `meshtastic-api` (or your preferred name)
- **Region**: Same as database region
- **Set up PostgreSQL**: No (already done)
- **Deploy now**: No

### 2. Configure Environment

Edit `fly.toml` if needed:

```toml
app = "meshtastic-api"
primary_region = "ord"

[build]
  dockerfile = "Dockerfile"

[env]
  PORT = "8000"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = false
  auto_start_machines = true
  min_machines_running = 1

[[vm]]
  cpu_kind = "shared"
  cpus = 1
  memory_mb = 512
```

### 3. Set Secrets

```bash
# Database URL
flyctl secrets set DATABASE_URL="postgres://username:password@meshtastic-db.internal:5432/database"

# Collector tokens (one per collector)
flyctl secrets set COLLECTOR_TOKEN_COLLECTOR1="your-secure-token-1"
flyctl secrets set COLLECTOR_TOKEN_COLLECTOR2="your-secure-token-2"

# Add more as needed
```

**Important**: Token names must match the collector_id in the format:
- Collector ID: `wichita-01` → Token name: `COLLECTOR_TOKEN_WICHITA_01`
- Collector ID: `nyc-collector` → Token name: `COLLECTOR_TOKEN_NYC_COLLECTOR`

### 4. Deploy Application

```bash
flyctl deploy
```

This will:
1. Build the Docker container
2. Push to Fly.io registry
3. Deploy to your region
4. Run database migrations
5. Start the API server

### 5. Verify Deployment

```bash
# Check app status
flyctl status

# Check health endpoint
curl https://meshtastic-api.fly.dev/health

# View logs
flyctl logs
```

## Deploy Background Processor

The processor normalizes raw events into domain tables.

### 1. Create Processor Machine

```bash
# Create a new machine for the processor
flyctl machine run \
  --app meshtastic-api \
  --dockerfile Dockerfile \
  --entrypoint "python processor.py" \
  --env PORT=8000
```

Alternatively, add to fly.toml:

```toml
[[services]]
  [[services.processes]]
    name = "processor"
    command = ["python", "processor.py", "--interval", "60"]
```

### 2. Verify Processor is Running

```bash
flyctl logs --app meshtastic-api | grep processor
```

## Configuration

### Scaling

#### Vertical Scaling (More Resources)

```bash
# Upgrade to 1GB RAM
flyctl scale memory 1024

# Upgrade to 2 CPUs
flyctl scale vm dedicated-cpu-2x
```

#### Horizontal Scaling (More Machines)

```bash
# Scale to 2 machines for redundancy
flyctl scale count 2

# Scale to different regions
flyctl regions add sea iad
flyctl scale count 3
```

### Database Scaling

```bash
# Increase storage
flyctl volumes extend <volume-id> --size 20

# Upgrade PostgreSQL
flyctl postgres update --app meshtastic-db
```

## Monitoring

### View Logs

```bash
# Follow logs
flyctl logs -a meshtastic-api

# Filter by instance
flyctl logs -a meshtastic-api --instance <instance-id>

# Search logs
flyctl logs -a meshtastic-api | grep ERROR
```

### Metrics

View metrics in Fly.io dashboard:
```bash
flyctl dashboard
```

Or use the Metrics API:
```bash
flyctl metrics -a meshtastic-api
```

### Check Database Size

```bash
flyctl postgres connect -a meshtastic-db

# In psql:
SELECT
    pg_database.datname,
    pg_size_pretty(pg_database_size(pg_database.datname)) AS size
FROM pg_database;

# Check table sizes:
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

## Maintenance

### Update Application

```bash
# Make code changes, then:
flyctl deploy

# Or force rebuild:
flyctl deploy --build-only
```

### Restart Application

```bash
flyctl apps restart meshtastic-api
```

### Database Backups

Fly.io automatically backs up PostgreSQL, but you can also:

```bash
# Manual backup
flyctl postgres backup -a meshtastic-db

# Restore from backup
flyctl postgres restore -a meshtastic-db --backup-id <id>
```

### Database Migrations

When you update schema.sql:

```bash
# Connect to database
flyctl postgres connect -a meshtastic-db

# Run your migration
\i /path/to/schema.sql
```

Or use the API startup migration (already configured in main.py).

## Security

### Rotate Collector Tokens

```bash
# Generate new token
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Update secret
flyctl secrets set COLLECTOR_TOKEN_COLLECTOR1="new-token"

# Update collector configuration
```

### Review Access Logs

```bash
flyctl logs -a meshtastic-api | grep "POST /v1/ingest"
```

### Enable IP Restrictions (Optional)

Add to fly.toml:

```toml
[[services.http_checks]]
  interval = 10000
  method = "GET"
  path = "/health"
  protocol = "http"
  timeout = 5000
```

## Troubleshooting

### API Returns 500 Errors

Check logs:
```bash
flyctl logs -a meshtastic-api
```

Common issues:
- Database connection failed (check DATABASE_URL)
- Missing dependencies (rebuild with `flyctl deploy`)

### Database Connection Errors

```bash
# Verify database is running
flyctl status -a meshtastic-db

# Check connection string
flyctl secrets list
```

### High Memory Usage

Monitor with:
```bash
flyctl metrics -a meshtastic-api
```

If needed, scale up:
```bash
flyctl scale memory 1024
```

### Slow Queries

Connect to database and check:
```sql
-- Show slow queries
SELECT pid, now() - query_start AS duration, query
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY duration DESC;

-- Create missing indexes
CREATE INDEX IF NOT EXISTS idx_custom ON table_name(column);
```

## Cost Optimization

### Development Setup (Minimal Cost)

- 1 shared-cpu machine (API + processor)
- 10GB PostgreSQL volume
- 1 region

Estimated: ~$5-10/month

### Production Setup

- 2-3 machines across regions
- 20-50GB PostgreSQL volume
- Dedicated CPU for high load

Estimated: ~$20-50/month

### Tips

1. Use `auto_stop_machines` for low-traffic periods
2. Clean up old events_raw data regularly
3. Use connection pooling (already configured)
4. Monitor and optimize slow queries

## API Endpoints

After deployment, your API will be available at:

```
https://your-app.fly.dev
```

### Public Endpoints

- `GET /health` - Health check
- `GET /v1/stats` - System statistics
- `GET /v1/network-stats?hours=24` - Network statistics
- `GET /v1/nodes?limit=100` - Node list
- `GET /v1/nodes/{node_id}` - Node details
- `GET /v1/map/geojson?hours=24` - Map data
- `GET /v1/traceroutes` - Traceroute list
- `GET /v1/traceroutes/{trace_id}` - Trace details
- `GET /v1/topology?hours=24` - Topology data

### Private Endpoints

- `POST /v1/ingest/batch` - Collector ingestion (requires auth)

## Next Steps

- [Collector Setup Guide](collector-setup.md) - Set up collectors to send data
- [Jekyll Deployment Guide](jekyll-deployment.md) - Deploy the web interface
- [Integration Guide](integration.md) - Integrate with your code
