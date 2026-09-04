# Docker & Multi-Service Containerization — Adaptive Financial Risk Intelligence Engine

## 1. Overview & Service Architecture

The project is containerized into a multi-service stack orchestrated by **Docker Compose**, providing environment reproducibility, automated health checks, and cross-service discovery over an isolated bridge network (`risk_network`).

```
+-----------------------------------------------------------------------------------+
|                            Docker Network: risk_network                           |
|                                                                                   |
|  +--------------------+     +--------------------+     +-----------------------+  |
|  |    postgres:5432   |     |     redis:6379     |     |      mlflow:5000      |  |
|  |  (PostgreSQL DB)   |     |   (Feature Cache)  |     |   (Model Registry)    |  |
|  +---------^----------+     +---------^----------+     +-----------^-----------+  |
|            |                          |                            |              |
|            +--------------------------+----------------------------+              |
|                                       |                                           |
|                           +-----------+-----------+                               |
|                           |        api:8000       |                               |
|                           |  (FastAPI Risk Engine |                               |
|                           |   & Dashboard UI)     |                               |
|                           +-----------------------+                               |
+-----------------------------------------------------------------------------------+
```

---

## 2. Configured Services

### 1. `postgres` (Relational Storage)
- **Image**: `postgres:16-alpine`
- **Port**: `5432:5432`
- **Database**: `fraud_risk` | **User**: `fraud_user`
- **Persistent Volume**: `postgres_data:/var/lib/postgresql/data`
- **Health Check**: `pg_isready -U fraud_user -d fraud_risk`

### 2. `redis` (Low-Latency Online Feature Store)
- **Image**: `redis:7-alpine`
- **Port**: `6379:6379`
- **Persistent Volume**: `redis_data:/data`
- **Health Check**: `redis-cli ping`

### 3. `mlflow` (Experiment Tracking & Model Registry Server)
- **Dockerfile**: `docker/Dockerfile.mlflow`
- **Port**: `5000:5000`
- **Backend Store**: `sqlite:////mlflow/mlflow.db` (bind-mounted from `./mlflow.db`)
- **Artifacts Root**: `/mlflow/artifacts` (bind-mounted from `./mlruns`)
- **Health Check**: `curl -f http://localhost:5000/health`

### 4. `api` (FastAPI Real-Time Serving Layer)
- **Dockerfile**: `docker/Dockerfile.api` (Python 3.11 with OpenMP/C++ runtimes for XGBoost/LightGBM)
- **Port**: `8000:8000`
- **Endpoints**:
  - `POST /predict`: Real-time transaction scoring (<100ms SLA)
  - `POST /predict/batch`: Vectorized high-throughput batch scoring
  - `POST /explain`: SHAP-driven explainability
  - `GET /ui`: Interactive web dashboard
  - `GET /health` & `GET /ready`: Health check probes
- **Dependencies**: Starts only after `postgres`, `redis`, and `mlflow` report `healthy`.
- **Health Check**: `curl -f http://localhost:8000/health`

---

## 3. Operational Runbook & Commands

### 3.1 Build Images
```powershell
docker compose build
```

### 3.2 Start Services in Background
```powershell
docker compose up -d
```

### 3.3 Check Running Containers & Health Status
```powershell
docker compose ps
```

### 3.4 View Live Logs
```powershell
# View logs from all services
docker compose logs -f

# View logs from API specifically
docker compose logs -f api
```

### 3.5 Test Endpoints
```powershell
# FastAPI Health
curl http://localhost:8000/health

# MLflow Server
curl http://localhost:5000/health

# Web Dashboard (open in browser)
# http://localhost:8000/ui
```

### 3.6 Stop Services
```powershell
# Stop containers
docker compose stop

# Stop and remove containers and networks (preserves persistent volumes)
docker compose down
```
