# Go-Live Readiness Checklist

## Pre-Flight

### 1. Configuration
```bash
# Validate config loads cleanly
python -c "from agent_memory.config import load_config; c = load_config(); print(c)"

# Verify BGE-M3 endpoint (if enabled)
python -c "
import httpx
from agent_memory.config import load_config
c = load_config()
if c.embedding.enabled:
    resp = httpx.get(f'{c.embedding.normalized_endpoint()}/health', timeout=5)
    print('BGE-M3 status:', resp.status_code)
"

# Check whether the configured sqlite-vec path loads
python -c "
import sqlite3
from agent_memory.config import load_config
from agent_memory.retrieval.sqlvec import load_sqlite_vec
c = load_config()
conn = sqlite3.connect(':memory:')
print('sqlite-vec available:', load_sqlite_vec(conn, c.retrieval.sqlite_vec_path))
conn.close()
"
# If False and hybrid search is required, set retrieval.sqlite_vec_path in
# config.toml and restart.
```

### 2. Database Migrations
```bash
# Verify all migrations are applied
python -c "
import sqlite3
from agent_memory.config import load_config
c = load_config()
conn = sqlite3.connect(str(c.database.resolved_path()))
row = conn.execute('SELECT MAX(version) FROM schema_migrations').fetchone()
print(f'Schema version: {row[0]}')
conn.close()
"
```

### 3. Health Checks
```bash
# Liveness
curl -s http://127.0.0.1:8765/health/live

# Readiness
curl -s http://127.0.0.1:8765/health/ready

# Index status (admin token required)
curl -s http://127.0.0.1:8765/v1/admin/index/status \
    -H "x-admin-token: $AGENT_MEMORY_ADMIN_TOKEN"
```

### 4. Backup
```bash
# Create a pre-launch backup
python -m memoryctl backup create --target ~/backups/memory-$(date +%Y%m%d).db

# Verify
python -m memoryctl backup verify --target ~/backups/memory-$(date +%Y%m%d).db
```

## Launch

### 5. Start the Service
```bash
# Direct module entrypoint (recommended for development)
python -m agent_memory.main
# → uvicorn binds the [server] host/port from config.toml

# Or uvicorn directly
python -m uvicorn agent_memory.main:create_app --factory \
    --host 127.0.0.1 --port 8765

# Docker (production)
docker compose up -d
```

### 6. Verify Adapters Connect
```bash
# Pi adapter smoke test
python -c "
import sys; sys.path.insert(0, 'adapters')
from adapters.pi.pi_adapter import PiAdapter, PiAdapterConfig
a = PiAdapter(PiAdapterConfig(project_id='smoke-test'))
a.on_session_start('s-test', 'native-test')
a.on_session_end('s-test')
print('Pi adapter OK')
a.close()
"

# Codex adapter smoke test
python -c "
import sys; sys.path.insert(0, 'adapters')
from adapters.codex import CodexAdapter, CodexAdapterConfig
a = CodexAdapter(CodexAdapterConfig(project_id='smoke-test'))
a.on_session_start('s-test', 'native-test')
a.on_session_end('s-test')
print('Codex adapter OK')
a.close()
"

# OpenCode adapter smoke test
python -c "
import sys; sys.path.insert(0, 'adapters')
from adapters.opencode import OpenCodeAdapter, OpenCodeAdapterConfig
a = OpenCodeAdapter(OpenCodeAdapterConfig(project_id='smoke-test'))
a.on_session_start('s-test', 'native-test')
a.on_session_end('s-test')
print('OpenCode adapter OK')
a.close()
"
```

## Post-Launch Monitoring

### 7. Index Health
```bash
# Human-readable snapshot
python -m memoryctl index status

# Scriptable JSON output (CI / dashboards)
python -m memoryctl index status --json

# Drain a backlog of pending index jobs in one batch
python -m memoryctl index drain --batch-size 200

# Rebuild the full index (or just one project's chunks)
python -m memoryctl index rebuild
python -m memoryctl index rebuild --project-id my-project

# Reset specific failed jobs back to pending
python -m memoryctl jobs retry <job-id>
# Reset all failed jobs
python -m memoryctl jobs retry --all

# (HTTP equivalent, requires admin token)
curl -X POST http://127.0.0.1:8765/v1/admin/jobs/<job-id>/retry \
    -H "x-admin-token: $AGENT_MEMORY_ADMIN_TOKEN"
```

### 8. Governance Review
```bash
# Check for stale/duplicate/superseded knowledge
python -m memoryctl knowledge governance --project-id <project_id>

# Review pending candidates
python -m memoryctl pending list --project-id <project_id>
```

## Rollback Plan

1. Stop the service: `docker compose down` or `kill <pid>`
2. Restore last known-good backup:
   ```bash
   cp ~/backups/memory-<date>.db ~/.local/share/agent-memory/memory.db
   ```
3. Verify: `python -m memoryctl doctor`
4. Restart the service

## Observability

### Log Format
Structured JSON logs to stdout. Key fields:
- `ts` – ISO 8601 timestamp
- `level` – DEBUG / INFO / WARNING / ERROR
- `service` – module name
- `msg` – human-readable message
- `extra` – context-specific fields

### Metrics
| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| Pending index jobs | `GET /v1/admin/index/status` | > 100 |
| Vector availability | `GET /v1/admin/index/status` → `vector_available` | False if hybrid expected |
| Spool pending events | `~/.local/state/agent-memory/<agent>/meta.json` | > 1000 |
| DB file size | `du -h memory.db` | > 5 GB |
| Backup age | `ls -lt ~/backups/` | > 7 days |

### Alerting
- BGE-M3 endpoint unreachable for > 5 min → retrieval degrades to lexical-only
- `vector_available: false` when hybrid search expected → check `retrieval.sqlite_vec_path`
- Pending index jobs > 100 → dispatcher stuck; run `memoryctl index drain`
- Spool > 1000 events → server unreachable
- DB integrity_check failure → restore from backup immediately
