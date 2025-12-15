# SiteFlow Dashboard

A full-stack dashboard for managing Docker-based websites on a Hetzner server. Provides site provisioning, deployment, monitoring, and operational controls through a clean card-based UI.

## Features

- **Site Provisioning** - Create new sites with auto-detection of project type (Node.js, Python, WordPress, Static)
- **Multiple Deployment Methods** - Deploy from Git repositories, folder uploads, or ZIP files
- **Cloudflare Integration** - Automatic DNS records and tunnel hostname configuration
- **Uptime Kuma Integration** - Health monitoring with automatic monitor creation for new sites
- **Container Management** - Start, stop, restart containers directly from the UI
- **Audit Logging** - Track all actions with timestamps and outputs
- **Real-time Updates** - WebSocket-based live status updates
- **Landing Pages** - Auto-generated "Coming Soon" pages for sites without deployments

## Architecture

```
Internet -> Cloudflare Tunnel -> Caddy (reverse proxy) -> Docker containers -> Sites
                                      ^
                                      |
                              caddy-docker-proxy
                              (auto-discovers labels)
```

## Structure

```
siteflow-dashboard/
├── backend/           # FastAPI service
│   ├── app/
│   │   ├── routers/   # API endpoints
│   │   ├── services/  # Business logic
│   │   ├── schemas/   # Pydantic models
│   │   └── main.py    # App entry point
│   └── requirements.txt
├── frontend/          # React + Vite
│   └── src/
│       ├── components/  # UI components
│       ├── pages/       # Dashboard page
│       └── api/         # API hooks
├── docker-compose.yml   # Production deployment
└── Dockerfile
```

## Quick Start

### Production (Docker)

1. Clone the repository
2. Copy `.env.example` to `.env` and configure:
   ```env
   # Hetzner SSH
   HETZNER_HOST=your-server-ip
   HETZNER_USER=root
   HETZNER_KEY_PATH=/path/to/ssh/key

   # Paths on remote server
   REMOTE_SITES_ROOT=/opt/sites
   REMOTE_GATEWAY_ROOT=/opt/gateway
   REMOTE_CADDYFILE=/opt/gateway/Caddyfile

   # Cloudflare
   CF_ACCOUNT_ID=your-account-id
   CF_API_TOKEN=your-api-token
   CF_TUNNEL_ID=your-tunnel-id

   # Uptime Kuma
   KUMA_URL=http://uptime-kuma:3001
   KUMA_USERNAME=admin
   KUMA_PASSWORD=your-password

   # NAS Backup Monitoring (optional)
   NAS_HOST=192.168.1.x
   NAS_USER=user
   NAS_PASSWORD=password
   NAS_SHARE=volume1
   NAS_BACKUP_PATH=backups
   ```

3. Deploy:
   ```bash
   docker compose up -d --build
   ```

### Development

**Backend:**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## API Endpoints

### Sites
- `GET /api/sites/` - List all sites with container status
- `POST /api/sites/{site}/{action}` - Start/stop/restart a site
- `POST /api/sites/containers/{container}/{action}` - Control individual containers
- `POST /api/sites/caddy/reload` - Reload Caddy configuration

### Provisioning
- `GET /api/provision/templates` - List available templates
- `POST /api/provision/detect` - Auto-detect project type from Git URL
- `POST /api/provision/` - Create a new site
- `DELETE /api/provision/` - Remove a site

### Deployment
- `POST /api/deploy/github` - Deploy from Git repository
- `POST /api/deploy/upload` - Deploy from ZIP file
- `POST /api/deploy/folder` - Deploy from folder upload
- `POST /api/deploy/pull` - Pull latest changes

### Health & Monitoring
- `GET /api/health/` - Get Uptime Kuma monitor status for all sites
- `POST /api/health/monitors` - Create a monitor
- `DELETE /api/health/monitors/{site_name}` - Delete a monitor

### Audit
- `GET /api/audit/logs` - Query audit log with filters
- `POST /api/audit/cleanup` - Remove old audit entries

### WebSocket
- `WS /api/ws` - Real-time site status updates

## Site Templates

When provisioning, the system auto-detects project type:

| Type | Detection | Stack |
|------|-----------|-------|
| **Node.js** | `package.json` | Node 20 + MongoDB |
| **Python** | `requirements.txt`, `pyproject.toml`, `manage.py` | Python 3.12 + PostgreSQL |
| **WordPress** | `wp-config.php`, `wp-content/` | WordPress + MariaDB |
| **Static** | Default | Nginx |

## UI Overview

The dashboard displays sites as cards with:

- **Status Badge** - Running/Stopped/Degraded/Unknown
- **Health Checklist** - Container, Caddy, Cloudflare, and HTTP reachability status
- **Domain Links** - Clickable links to the live site
- **Quick Actions** - Start, Stop, Restart, View Logs, Deploy, Pull, Delete

### Provisioning Flow

1. Enter site name (lowercase, alphanumeric with hyphens)
2. Optionally specify a custom domain (defaults to `{name}.double232.com`)
3. Choose deployment source:
   - **Git** - Clone from repository URL
   - **Folder** - Upload a directory
   - **Zip** - Upload a ZIP archive
4. System auto-detects project type and provisions accordingly

If no deployment source is provided, a "Coming Soon" landing page is served.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `HETZNER_HOST` | Server IP address | Required |
| `HETZNER_USER` | SSH username | `root` |
| `HETZNER_KEY_PATH` | Path to SSH private key | Required |
| `REMOTE_SITES_ROOT` | Sites directory on server | `/opt/sites` |
| `REMOTE_GATEWAY_ROOT` | Gateway directory | `/opt/gateway` |
| `REMOTE_CADDYFILE` | Caddyfile path | `/opt/gateway/Caddyfile` |
| `CF_ACCOUNT_ID` | Cloudflare account ID | Optional |
| `CF_API_TOKEN` | Cloudflare API token | Optional |
| `CF_TUNNEL_ID` | Cloudflare tunnel ID | Optional |
| `KUMA_URL` | Uptime Kuma socket URL | `http://uptime-kuma:3001` |
| `KUMA_USERNAME` | Kuma login username | `admin` |
| `KUMA_PASSWORD` | Kuma login password | Required for monitoring |
| `SQLITE_DB_PATH` | Audit database path | `siteflow.db` |
| `CACHE_TTL_SECONDS` | Site cache TTL | `20` |
| `WS_MONITOR_INTERVAL` | WebSocket poll interval | `10.0` |

## How It Works

1. **Site Discovery** - Backend SSH's to server, scans `/opt/sites/*/docker-compose.yml`
2. **Container Matching** - Correlates compose services with running Docker containers
3. **Caddy Integration** - Uses `caddy-docker-proxy` which auto-discovers container labels
4. **Cloudflare Sync** - Adds/removes DNS records and tunnel hostnames on provision/deprovision
5. **Health Monitoring** - Queries Uptime Kuma via socket.io for HTTP health checks

## Backup System

SiteFlow includes a comprehensive backup system using restic for encrypted, deduplicated backups to a NAS via Tailscale.

### Features

- **Database Backups** - Daily mysqldump of all MariaDB/MySQL containers
- **Uploads Backups** - Daily backup of WordPress wp-content/uploads directories
- **30-day Retention** - Automatic pruning with keep-daily/weekly/monthly policies
- **Verification** - Weekly integrity checks with data sampling
- **VM Snapshots** - Optional weekly Hetzner Cloud snapshots
- **Dashboard Integration** - Backup status displayed on site cards

### Installation

```bash
# On the webserver
cd /opt/siteflow-backups
cp config.env.example config.env
# Edit config.env with your NAS credentials
./install.sh

# Enable automated backups
cp systemd/* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now siteflow-backup-db.timer
systemctl enable --now siteflow-backup-uploads.timer
systemctl enable --now siteflow-backup-verify.timer
```

### Manual Operations

```bash
# Run backup manually
/opt/siteflow-backups/backup_db.sh
/opt/siteflow-backups/backup_uploads.sh

# Verify repository
/opt/siteflow-backups/verify_backups.sh

# List snapshots
restic -r /mnt/nas_backups/restic/webserver --password-file /root/.restic-pass snapshots

# Restore (dry run first!)
/opt/siteflow-backups/restore.sh --site myblog --timestamp latest --restore-uploads --dry-run
/opt/siteflow-backups/restore.sh --site myblog --timestamp latest --restore-uploads --i-understand-risk
```

### Backup Schedule

| Job | Schedule | Retention |
|-----|----------|-----------|
| Database | Daily 2:00 AM | 30 daily, 4 weekly, 6 monthly |
| Uploads | Daily 3:30 AM | 30 daily, 4 weekly, 6 monthly |
| Verify | Sunday 5:00 AM | N/A |
| Snapshot | Sunday 12:00 AM | 4 weeks |

### Troubleshooting

```bash
# Check timer status
systemctl list-timers --all | grep siteflow

# View logs
journalctl -u siteflow-backup-db -f
journalctl -u siteflow-backup-uploads -f

# Check mount
mount | grep nas_backups
df -h /mnt/nas_backups

# Manual mount if needed
mount /mnt/nas_backups
```

## Requirements

- Docker and Docker Compose on target server
- `caddy-docker-proxy` running on `web_proxy` network
- Cloudflare tunnel (cloudflared) for external access
- Uptime Kuma for health monitoring
- SSH access to the target server
- NAS with SMB share (for backups)
- Tailscale for secure NAS connectivity

## License

MIT
