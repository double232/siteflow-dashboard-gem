# SiteFlow Dashboard

A full-stack dashboard that visualizes every website deployed on the Hetzner server as an interactive flow (Cloudflare Tunnel → Domains → Caddy Gateway → Docker containers → Sites). It also lets you trigger operational actions (container controls, Caddy reload) directly from the UI.

## Structure

```
siteflow-dashboard/
├── backend/   # FastAPI service that talks to Hetzner + Cloudflare
└── frontend/  # Vite + React + React Flow graph UI
```

## Backend

1. Create a virtual environment and install dependencies:
   ```bash
   cd backend
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in:
   - `HETZNER_HOST`, `HETZNER_KEY_PATH`, etc.
   - Optional `CF_*` values for Cloudflare tunnel insights.
3. Run the API:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

### API Highlights
- `GET /api/sites` → aggregated site/container/Caddy data (cached; force refresh via `?refresh=true`).
- `GET /api/graph` → nodes/edges ready for the React Flow canvas.
- `POST /api/sites/containers/{name}/{start|stop|restart|logs}` → one-click controls.
- `POST /api/sites/caddy/reload` → redeploy gateway config.

The Hetzner integration lists `/opt/sites`, parses each `docker-compose.yml`, matches live Docker containers, and maps Caddy reverse proxies to upstream services. Optional Cloudflare integration queries tunnel details (hostnames + active connectors) and threads them into the flow graph.

## Frontend

1. Install deps & run the dev server:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
2. Set `VITE_API_BASE_URL` (defaults to `http://localhost:8000`). The dev server proxies `/api/*` automatically.
3. Build for production via `npm run build` (output → `frontend/dist`).

### UI Features
- **Flow Canvas**: React Flow + Dagre auto-layout for Tunnel → Domain → Caddy → Container → Site. Nodes are color-coded, status-tagged, and clickable.
- **Site List**: left rail that tracks every deployment with domain/container counts.
- **Inspector Panel**: shows domains, compose path, per-container controls, and the output of the last action.
- **Global Controls**: refresh both datasets and reload Caddy without SSH.

## Deployment Notes
- Keep `.env` on the backend only; the frontend never sees SSH or Cloudflare secrets.
- Recommend running FastAPI behind systemd/Gunicorn/Uvicorn and serving the compiled frontend via Caddy or the existing gateway.
- Point production builds at the remote API by setting `VITE_API_BASE_URL=https://<your-api-host>` before `npm run build`.

## Next Steps
1. Extend actions to provision/deprovision via your automation scripts.
2. Persist action/audit history (SQLite/Postgres).
3. Add WebSocket pushes for instant status changes.
4. Overlay performance metrics (CPU/memory) per container in the node metadata.
