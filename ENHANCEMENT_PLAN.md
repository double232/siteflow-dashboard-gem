# SiteFlow Dashboard Enhancement Plan

## Overview

Implement three major features for the siteflow-dashboard:
1. **WebSockets** - Replace 60s polling with real-time updates
2. **Audit Logging + Full Lifecycle Provisioning** - SQLite database, action history, site create/destroy
3. **Graph Enhancements** - Container metrics (CPU/mem) and NAS backup status nodes

---

## Phase 1: Database Layer (SQLite)

### New Files
- `backend/app/database.py` - SQLAlchemy models, DB init

### Schema
```
AuditLog: id, timestamp, action_type, target_type, target_name, status, output, error_message, metadata_json, duration_ms
```

### Config Updates (`backend/app/config.py`)
- `sqlite_db_path`, `audit_retention_days`, `audit_max_output_length`
- `nas_host`, `nas_user`, `nas_password`, `nas_backup_root`, `nas_stale_threshold_hours`

---

## Phase 2: Backend Services

### New Services
| File | Purpose |
|------|---------|
| `services/audit.py` | AuditService - log actions, query logs, cleanup |
| `services/provision.py` | ProvisionService - create/destroy sites with templates |
| `services/metrics_service.py` | MetricsService - docker stats collection |
| `services/nas_service.py` | NASService - SSH to NAS for backup status |
| `services/event_bus.py` | EventBus - pub/sub for WebSocket broadcasts |
| `services/monitor.py` | SiteMonitor - background task for change detection |

### New Schemas
| File | Models |
|------|--------|
| `schemas/audit.py` | AuditLogEntry, AuditLogResponse, AuditLogFilter |
| `schemas/provision.py` | ProvisionRequest, DeprovisionRequest, SiteTemplate |
| `schemas/metrics.py` | ContainerMetrics, SiteMetrics, MetricsResponse |
| `schemas/backup.py` | BackupInfo, NASStatus |

### Updated Schemas
- `schemas/graph.py` - Add NodeMetrics, BackupStatus to GraphNode

---

## Phase 3: Backend Routers

### New Routers
| File | Endpoints |
|------|-----------|
| `routers/audit.py` | `GET /api/audit/logs` (pagination, filters) |
| `routers/provision.py` | `POST /api/provision/`, `DELETE /api/provision/`, `GET /api/provision/templates` |
| `routers/ws.py` | `WS /api/ws` (WebSocket endpoint) |

### Updated Routers
- `routers/sites.py` - Add audit logging to container actions
- `routers/graph.py` - Integrate metrics and NAS data

### main.py Updates
- Register new routers
- Add lifespan events for SiteMonitor start/stop
- Init database on startup

---

## Phase 4: WebSocket Protocol

### Message Types (Server -> Client)
- `sites.update` - Full sites state push
- `graph.update` - Full graph state push
- `action.output` - Streaming action output
- `error` - Error notification

### Message Types (Client -> Server)
- `subscribe` / `unsubscribe` - Topic management
- `action.start` - Execute container action with streaming
- `ping` - Keepalive

### Backend Architecture
- `EventBus` with WeakSet subscribers per topic
- `SiteMonitor` polls every 10s, broadcasts changes
- `ConnectionManager` tracks active WebSocket connections

---

## Phase 5: Frontend Infrastructure

### New Files
| File | Purpose |
|------|---------|
| `api/websocket.ts` | WebSocketClient class with reconnection |
| `api/WebSocketContext.tsx` | React context for WS state |
| `api/types/audit.ts` | Audit TypeScript types |
| `api/types/provision.ts` | Provision TypeScript types |
| `components/AuditLog.tsx` | Audit log table with filters |
| `components/ProvisionForm.tsx` | New site provisioning form |
| `components/DeprovisionConfirm.tsx` | Deprovision confirmation dialog |
| `components/MetricsBar.tsx` | CPU/memory progress bar |
| `components/BackupBadge.tsx` | Backup status indicator |

### Updated Files
- `main.tsx` - Wrap with WebSocketProvider
- `api/hooks.ts` - Add audit/provision hooks, conditional polling
- `api/types.ts` - Add NodeMetrics, BackupStatus
- `components/nodes/StatusNode.tsx` - Display metrics, backup status, color-coding
- `components/FlowCanvas.tsx` - Add NAS node rank

---

## Phase 6: Site Templates (All with CMS)

### Available Templates
| Template | Stack | CMS | Description |
|----------|-------|-----|-------------|
| `static` | Nginx + Decap CMS | Decap (formerly Netlify CMS) | Git-based static site with visual editor |
| `node` | Payload CMS | Payload | Headless TypeScript CMS with admin UI |
| `python` | Wagtail | Wagtail | Django-based CMS with page builder |
| `wordpress` | WordPress + MariaDB | WordPress | Full WordPress with database |

### Template Details

#### Static (Decap CMS)
- Nginx serving static files
- Decap CMS admin at `/admin`
- Git-based content storage
- Markdown/YAML content files
- Best for: blogs, documentation, landing pages

#### Node (Payload CMS)
- Payload CMS (TypeScript)
- MongoDB for content storage
- REST + GraphQL APIs
- Admin UI at `/admin`
- Best for: headless apps, APIs, custom content types

#### Python (Wagtail)
- Django + Wagtail CMS
- PostgreSQL database
- StreamField page builder
- Admin at `/admin`
- Best for: complex sites, multi-page content

#### WordPress
- WordPress + MariaDB
- Full plugin ecosystem
- WP Admin at `/wp-admin`
- Volume mounts for wp-content
- Best for: traditional blogs, WooCommerce, client sites

### Provisioning Flow
1. Create `/opt/sites/{name}/` directory
2. Generate docker-compose.yml from template (includes CMS + database services)
3. Create required subdirectories (uploads, content, etc.)
4. Append Caddy route to Caddyfile
5. `docker compose up -d`
6. Wait for database initialization
7. Reload Caddy

### Deprovisioning Flow
1. `docker compose down -v` (remove volumes if requested)
2. Remove Caddy route
3. Optionally delete files and database data
4. Reload Caddy

---

## Implementation Order

### Step 1: Database + Audit (Backend)
1. Create `database.py` with AuditLog model
2. Update `config.py` with new settings
3. Create `schemas/audit.py`
4. Create `services/audit.py`
5. Create `routers/audit.py`
6. Integrate audit into `routers/sites.py`
7. Update `main.py` to init DB and register router

### Step 2: Provisioning (Backend)
1. Create `schemas/provision.py`
2. Create `services/provision.py` with templates
3. Create `routers/provision.py`
4. Update `dependencies.py`

### Step 3: Metrics + NAS (Backend)
1. Create `schemas/metrics.py` and `schemas/backup.py`
2. Create `services/metrics_service.py`
3. Create `services/nas_service.py`
4. Update `schemas/graph.py` with NodeMetrics, BackupStatus
5. Update `services/graph_builder.py` to include metrics/NAS
6. Update `routers/graph.py` to fetch all data

### Step 4: WebSocket (Backend)
1. Create `services/event_bus.py`
2. Create `services/monitor.py`
3. Create `routers/ws.py`
4. Update `main.py` with lifespan events

### Step 5: Frontend Updates
1. Create TypeScript types for audit, provision
2. Add API hooks for audit, provision
3. Create WebSocket client and context
4. Create AuditLog, ProvisionForm, DeprovisionConfirm components
5. Create MetricsBar, BackupBadge components
6. Update StatusNode with metrics display
7. Update FlowCanvas for NAS node
8. Update main.tsx with WebSocketProvider
9. Add CSS styles

---

## Critical Files to Modify

### Backend
- `backend/app/config.py`
- `backend/app/main.py`
- `backend/app/dependencies.py`
- `backend/app/routers/sites.py`
- `backend/app/routers/graph.py`
- `backend/app/services/graph_builder.py`
- `backend/app/schemas/graph.py`

### Frontend
- `frontend/src/main.tsx`
- `frontend/src/api/hooks.ts`
- `frontend/src/api/types.ts`
- `frontend/src/components/nodes/StatusNode.tsx`
- `frontend/src/components/FlowCanvas.tsx`
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/index.css`

---

## Configuration Required

### backend/.env additions
```
# Database
SQLITE_DB_PATH=siteflow.db
AUDIT_RETENTION_DAYS=90

# NAS
NAS_HOST=192.168.1.246
NAS_USER=evan
NAS_PASSWORD=BOLeiDGOGyT*j6
NAS_BACKUP_ROOT=/volume1/backups
NAS_STALE_THRESHOLD_HOURS=48

# WebSocket
WS_MONITOR_INTERVAL=10.0
```
