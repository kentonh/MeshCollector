# Federated Meshtastic System

A complete federated packet aggregation system for Meshtastic networks with distributed collectors, central API, and public web explorer.

## Overview

This system enables you to:
- Collect Meshtastic packets from multiple geographically distributed locations
- Aggregate data reliably through a central API
- Visualize the network through a public Jekyll website with:
  - Node list with filtering and search
  - Interactive map with node positions
  - Traceroute explorer for route analysis
  - Network topography graph showing connections

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Collector 1    │     │  Collector 2    │     │  Collector N    │
│  (Raspberry Pi) │     │  (Raspberry Pi) │     │  (Raspberry Pi) │
│                 │     │                 │     │                 │
│  ┌──────────┐   │     │  ┌──────────┐   │     │  ┌──────────┐   │
│  │ Meshtastic│  │     │  │ Meshtastic│  │     │  │ Meshtastic│  │
│  │   Node    │  │     │  │   Node    │  │     │  │   Node    │  │
│  └─────┬────┘   │     │  └─────┬────┘   │     │  └─────┬────┘   │
│        │        │     │        │        │     │        │        │
│  ┌─────▼────┐   │     │  ┌─────▼────┐   │     │  ┌─────▼────┐   │
│  │  Packet  │   │     │  │  Packet  │   │     │  │  Packet  │   │
│  │ Collector│   │     │  │ Collector│   │     │  │ Collector│   │
│  └─────┬────┘   │     │  └─────┬────┘   │     │  └─────┬────┘   │
│        │        │     │        │        │     │        │        │
│  ┌─────▼────┐   │     │  ┌─────▼────┐   │     │  ┌─────▼────┐   │
│  │  Outbox  │   │     │  │  Outbox  │   │     │  │  Outbox  │   │
│  │ (SQLite) │   │     │  │ (SQLite) │   │     │  │ (SQLite) │   │
│  └─────┬────┘   │     │  └─────┬────┘   │     │  └─────┬────┘   │
│        │        │     │        │        │     │        │        │
│  ┌─────▼────┐   │     │  ┌─────▼────┐   │     │  ┌─────▼────┐   │
│  │ Uploader │   │     │  │ Uploader │   │     │  │ Uploader │   │
│  │ Service  │   │     │  │ Service  │   │     │  │ Service  │   │
│  └─────┬────┘   │     │  └─────┬────┘   │     │  └─────┬────┘   │
└────────┼────────┘     └────────┼────────┘     └────────┼────────┘
         │                       │                       │
         │                       │                       │
         └───────────────────────┴───────────────────────┘
                                 │
                                 │ HTTPS/gzip
                                 │
                          ┌──────▼──────┐
                          │  Central    │
                          │  API        │
                          │  (Fly.io)   │
                          │             │
                          │  ┌───────┐  │
                          │  │FastAPI│  │
                          │  └───┬───┘  │
                          │      │      │
                          │  ┌───▼───┐  │
                          │  │Postgres│ │
                          │  └───┬───┘  │
                          │      │      │
                          │  ┌───▼───┐  │
                          │  │Process│  │
                          │  │  or   │  │
                          │  └───────┘  │
                          └──────┬──────┘
                                 │
                                 │ Public API
                                 │
                          ┌──────▼──────┐
                          │   Jekyll    │
                          │   Website   │
                          │ (GitHub     │
                          │  Pages)     │
                          │             │
                          │  /nodes     │
                          │  /map       │
                          │  /traceroute│
                          │  /topography│
                          └─────────────┘
```

## Components

### 1. Collector (`collector/`)
Python scripts that run on Raspberry Pi or similar devices:
- `outbox.py` - Manages the outbox table for reliable queuing
- `uploader.py` - Uploads events to the central API with retry logic
- `schema.sql` - SQLite database schema for the outbox
- `meshtastic-uploader.service` - systemd service configuration

### 2. Central API (`api/`)
FastAPI application deployed on Fly.io:
- `main.py` - API endpoints for ingestion and public queries
- `processor.py` - Background processor for data normalization
- `schema.sql` - PostgreSQL database schema
- `Dockerfile` - Container configuration
- `fly.toml` - Fly.io deployment configuration

### 3. Jekyll Website (`jekyll-site/`)
Static website for public network exploration:
- `/` - Dashboard with statistics
- `/nodes/` - Searchable node list
- `/map/` - Interactive Leaflet map
- `/traceroutes/` - Route explorer
- `/topography/` - Network graph visualization

## Quick Start

### Prerequisites
- Python 3.9+
- PostgreSQL (via Fly.io)
- Fly.io account
- GitHub account (for Jekyll hosting)

### 1. Deploy Central API

```bash
cd api
flyctl launch
flyctl postgres create
flyctl secrets set DATABASE_URL=<your-postgres-url>
flyctl secrets set COLLECTOR_TOKEN_collector1=<your-token>
flyctl deploy
```

### 2. Set Up Collector

```bash
cd collector
pip install -r requirements.txt
python3 uploader.py \
  --api-url https://your-app.fly.dev \
  --collector-id collector-01 \
  --token <your-token> \
  --db-path /path/to/collector.sqlite
```

### 3. Deploy Jekyll Site

```bash
cd jekyll-site
# Edit _config.yml to set your API URL
# Push to GitHub and enable GitHub Pages
```

## Features

### Data Collection
- **Reliable Uploads**: Outbox pattern with automatic retries
- **Deduplication**: SHA256-based event IDs prevent duplicates
- **Compression**: Gzip compression for efficient bandwidth usage
- **Resilience**: Survives network outages with local queuing

### API
- **Ingestion**: POST /v1/ingest/batch for collector uploads
- **Public Queries**: RESTful endpoints for nodes, map, traces, topology
- **Authentication**: Per-collector Bearer tokens
- **Scalability**: PostgreSQL backend with connection pooling

### Website
- **Real-time**: Auto-refreshing data every 30-60 seconds
- **Interactive**: Filterable tables, zoomable map, draggable graph
- **Responsive**: Mobile-friendly design
- **Privacy**: Coordinate rounding and no message payloads

## Documentation

- [Collector Setup Guide](docs/collector-setup.md)
- [API Deployment Guide](docs/api-deployment.md)
- [Jekyll Deployment Guide](docs/jekyll-deployment.md)
- [Integration Guide](docs/integration.md)

## Privacy & Security

- Coordinates are rounded to ~100m precision by default
- Message payloads are never exposed on the public website
- Only metadata and statistics are published
- Per-collector authentication with unique tokens
- HTTPS for all communications

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - see LICENSE file for details

## Acknowledgments

- [Meshtastic](https://meshtastic.org) - Long range, low power mesh networking
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [Leaflet](https://leafletjs.com/) - Interactive map library
- [D3.js](https://d3js.org/) - Data visualization library
- [Jekyll](https://jekyllrb.com/) - Static site generator
