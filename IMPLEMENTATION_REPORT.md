# SiteFlow Dashboard Enhancement - Implementation Report

## Overview

This report documents the implementation of three major features for the siteflow-dashboard:

1. **WebSockets** - Real-time updates replacing 60s polling
2. **Audit Logging + Full Lifecycle Provisioning** - SQLite database, action history, site create/destroy
3. **Graph Enhancements** - Container metrics (CPU/mem) and NAS backup status nodes

---

## Backend Changes

### New Files Created

| File | Purpose |
|------|---------|
| `backend/app/database.py` | SQLAlchemy models and database management (AuditLog table) |
| `backend/app/schemas/audit.py` | Audit log Pydantic schemas (AuditLogEntry, AuditLogFilter, AuditLogResponse) |
| `backend/app/schemas/provision.py` | Provisioning schemas and 4 CMS templates |
| `backend/app/schemas/metrics.py` | Container metrics schemas (ContainerMetrics, SiteMetrics) |
| `backend/app/schemas/backup.py` | NAS backup status schemas (BackupInfo, NASStatus) |
| `backend/app/services/audit.py` | AuditService - log actions, query logs, cleanup old entries |
| `backend/app/services/provision.py` | ProvisionService - create/destroy sites with docker-compose templates |
| `backend/app/services/metrics_service.py` | MetricsService - docker stats collection via SSH |
| `backend/app/services/nas_service.py` | NASService - SSH to NAS for backup status monitoring |
| `backend/app/services/event_bus.py` | EventBus and ConnectionManager for WebSocket pub/sub |
| `backend/app/services/monitor.py` | SiteMonitor - background task polling every 10s, broadcasts changes |
| `backend/app/routers/audit.py` | `GET /api/audit/logs` with pagination and filters |
| `backend/app/routers/provision.py` | `POST /api/provision/`, `DELETE /api/provision/`, `GET /api/provision/templates` |
| `backend/app/routers/ws.py` | `WS /api/ws` - WebSocket endpoint for real-time updates |

### Modified Files

| File | Changes |
|------|---------|
| `backend/app/config.py` | Added database, NAS, and WebSocket settings |
| `backend/app/main.py` | Added lifespan events for monitor start/stop, DB init, registered new routers |
| `backend/app/dependencies.py` | Added get_audit_service, get_provision_service, get_metrics_service, get_nas_service |
| `backend/app/routers/sites.py` | Integrated audit logging for container actions and Caddy reload |
| `backend/app/routers/graph.py` | Added metrics and NAS data fetching in parallel |
| `backend/app/schemas/graph.py` | Added NodeMetrics, NodeBackupStatus to GraphNode; added nas_connected/nas_error to GraphResponse |
| `backend/app/services/graph_builder.py` | Integrated metrics and backup status into graph nodes, added NAS node |
| `backend/requirements.txt` | Added sqlalchemy==2.0.36, websockets==13.1 |

### Database Schema

```sql
CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    target_type VARCHAR(50) NOT NULL,
    target_name VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL,
    output TEXT,
    error_message TEXT,
    metadata_json TEXT,
    duration_ms FLOAT
);

-- Indexes on: timestamp, action_type, target_type, target_name, status
```

### Site Templates

| Template | Stack | CMS | Best For |
|----------|-------|-----|----------|
| `static` | Nginx + Decap CMS | Decap (formerly Netlify CMS) | Blogs, documentation, landing pages |
| `node` | Node.js + Payload + MongoDB | Payload CMS | Headless apps, APIs, custom content types |
| `python` | Django + Wagtail + PostgreSQL | Wagtail | Complex sites, multi-page content |
| `wordpress` | WordPress + MariaDB | WordPress | Traditional blogs, WooCommerce, client sites |

### WebSocket Protocol

**Server -> Client Messages:**
- `sites.update` - Full sites state push
- `graph.update` - Full graph state push
- `action.output` - Streaming action output with status (started/completed/failed)
- `error` - Error notification

**Client -> Server Messages:**
- `subscribe` / `unsubscribe` - Topic management
- `action.start` - Execute container action with streaming
- `ping` - Keepalive (server responds with `pong`)

---

## Frontend Changes

### New Files Created

| File | Purpose |
|------|---------|
| `frontend/src/api/types/audit.ts` | Audit TypeScript types |
| `frontend/src/api/types/provision.ts` | Provision TypeScript types |
| `frontend/src/api/websocket.ts` | WebSocketClient class with auto-reconnection |
| `frontend/src/api/WebSocketContext.tsx` | React context for WebSocket state management |
| `frontend/src/components/AuditLog.tsx` | Audit log table with filters and pagination |
| `frontend/src/components/ProvisionForm.tsx` | New site provisioning form with template selection |
| `frontend/src/components/DeprovisionConfirm.tsx` | Deprovision confirmation dialog with safety checks |
| `frontend/src/components/MetricsBar.tsx` | CPU/memory progress bar component |
| `frontend/src/components/BackupBadge.tsx` | Backup status indicator with relative time |

### Modified Files

| File | Changes |
|------|---------|
| `frontend/src/api/types.ts` | Added NodeMetrics, NodeBackupStatus, WebSocketMessage, ActionOutputMessage |
| `frontend/src/api/hooks.ts` | Added useAuditLogs, useTemplates, useProvisionSite, useDeprovisionSite; added conditional polling for WebSocket |
| `frontend/src/main.tsx` | Wrapped app with WebSocketProvider |
| `frontend/src/components/nodes/StatusNode.tsx` | Display metrics bar and backup badge; added NAS node color |
| `frontend/src/components/FlowCanvas.tsx` | Added NAS node to KIND_RANK; pass metrics/backup to node data |
| `frontend/src/index.css` | Added styles for MetricsBar, BackupBadge, AuditLog, ProvisionForm, DeprovisionConfirm, WebSocket status |

---

## API Endpoints

### Audit Endpoints

```
GET /api/audit/logs
    Query params: page, page_size, action_type, target_type, target_name, status, start_date, end_date
    Response: { logs: [], total, page, page_size, total_pages }

POST /api/audit/cleanup
    Response: { deleted: number, message: string }
```

### Provision Endpoints

```
GET /api/provision/templates
    Response: { templates: [{ id, name, description, cms, stack, best_for, required_services }] }

POST /api/provision/
    Body: { name, template, domain?, environment? }
    Response: { name, template, status, message, path?, domain? }

DELETE /api/provision/
    Body: { name, remove_volumes?, remove_files? }
    Response: { name, status, message, volumes_removed, files_removed }
```

### WebSocket Endpoint

```
WS /api/ws
    - Receives real-time sites.update and graph.update messages
    - Can send action.start to execute container actions
    - Automatic reconnection with exponential backoff
```

---

## Configuration

### New Environment Variables

Add to `backend/.env`:

```bash
# Database
SQLITE_DB_PATH=siteflow.db
AUDIT_RETENTION_DAYS=90
AUDIT_MAX_OUTPUT_LENGTH=10000

# NAS (optional - for backup monitoring)
NAS_HOST=192.168.1.246
NAS_USER=evan
NAS_PASSWORD=your_secure_password
NAS_BACKUP_ROOT=/volume1/backups
NAS_STALE_THRESHOLD_HOURS=48

# WebSocket
WS_MONITOR_INTERVAL=10.0
```

---

## Installation

### Backend

```bash
cd backend
pip install -r requirements.txt
```

### Frontend

No new npm packages required - all dependencies were already present.

---

## Usage

### Starting the Backend

```bash
cd backend
uvicorn app.main:app --reload
```

The database will be automatically created on startup.

### Starting the Frontend

```bash
cd frontend
npm run dev
```

### Provisioning a New Site

1. Click "New Site" button (to be added to Dashboard)
2. Enter site name (lowercase, alphanumeric with hyphens)
3. Select template (Static, Node, Python, WordPress)
4. Optionally add domain
5. Click "Provision Site"

### Viewing Audit Logs

Navigate to the Audit Log panel to see:
- All container actions (start/stop/restart/logs)
- Caddy reload events
- Site provisioning/deprovisioning
- Duration and status of each action

### WebSocket Real-time Updates

Once connected, the dashboard will:
- Stop polling every 60 seconds
- Receive instant updates when sites/containers change
- Show live action output when executing commands

---

## Architecture

```
Frontend (React + TypeScript)
    |
    +-- WebSocketProvider (real-time updates)
    |       |
    |       +-- WebSocketClient (auto-reconnect)
    |
    +-- React Query (data fetching + cache)
            |
            v
Backend (FastAPI + Python)
    |
    +-- SiteMonitor (background polling)
    |       |
    |       +-- EventBus (pub/sub)
    |               |
    |               +-- ConnectionManager (WebSocket connections)
    |
    +-- Services
    |       |
    |       +-- HetznerService (SSH to server)
    |       +-- MetricsService (docker stats)
    |       +-- NASService (SSH to NAS)
    |       +-- AuditService (SQLite logging)
    |       +-- ProvisionService (site lifecycle)
    |
    +-- SQLite Database (audit logs)
```

---

## File Structure

```
siteflow-dashboard/
├── backend/
│   └── app/
│       ├── database.py          [NEW]
│       ├── config.py            [MODIFIED]
│       ├── main.py              [MODIFIED]
│       ├── dependencies.py      [MODIFIED]
│       ├── routers/
│       │   ├── audit.py         [NEW]
│       │   ├── provision.py     [NEW]
│       │   ├── ws.py            [NEW]
│       │   ├── sites.py         [MODIFIED]
│       │   └── graph.py         [MODIFIED]
│       ├── schemas/
│       │   ├── audit.py         [NEW]
│       │   ├── provision.py     [NEW]
│       │   ├── metrics.py       [NEW]
│       │   ├── backup.py        [NEW]
│       │   └── graph.py         [MODIFIED]
│       └── services/
│           ├── audit.py         [NEW]
│           ├── provision.py     [NEW]
│           ├── metrics_service.py [NEW]
│           ├── nas_service.py   [NEW]
│           ├── event_bus.py     [NEW]
│           ├── monitor.py       [NEW]
│           └── graph_builder.py [MODIFIED]
│
└── frontend/
    └── src/
        ├── main.tsx             [MODIFIED]
        ├── index.css            [MODIFIED]
        ├── api/
        │   ├── types.ts         [MODIFIED]
        │   ├── hooks.ts         [MODIFIED]
        │   ├── websocket.ts     [NEW]
        │   ├── WebSocketContext.tsx [NEW]
        │   └── types/
        │       ├── audit.ts     [NEW]
        │       └── provision.ts [NEW]
        └── components/
            ├── AuditLog.tsx     [NEW]
            ├── ProvisionForm.tsx [NEW]
            ├── DeprovisionConfirm.tsx [NEW]
            ├── MetricsBar.tsx   [NEW]
            ├── BackupBadge.tsx  [NEW]
            ├── FlowCanvas.tsx   [MODIFIED]
            └── nodes/
                └── StatusNode.tsx [MODIFIED]
```

---

## Version

- API Version: 0.2.0
- Implementation Date: December 2024
