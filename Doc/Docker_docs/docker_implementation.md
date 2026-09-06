# Docker & Multi-Service Containerization — Adaptive Financial Risk Intelligence Engine

## 1. Overview & Service Architecture

The project is containerized into a multi-service stack orchestrated by **Docker Compose**, providing environment reproducibility, automated health checks, and cross-service discovery over an isolated bridge network (`risk_network`).

```
+--------------------------------------------------------------------------------------------------+
|                                    Docker Network: risk_network                                  |
|                                                                                                  |
|  +--------------------+     +--------------------+     +--------------------------------------+  |
|  |    postgres:5432   |     |     redis:6379     |     |             mlflow:5000              |  |
|  |  (PostgreSQL DB)   |     |   (Feature Cache)  |     | (Model Registry & Experiment Store)  |  |
|  +---------^----------+     +---------^----------+     +------------------^-------------------+  |
|            |                          |                                   |                      |
|            +--------------------------+-----------------------------------+                      |
|            |                                                              |                      |
|  +---------v-----------+                                        +---------v-----------+          |
|  |        api:8000     |                                        |     airflow:8080    |          |
|  | (FastAPI Scoring &  |                                        | (Orchestration DAGs |          |
|  |   Risk Dashboard)   |                                        |  & Automated ML)    |          |
|  +---------------------+                                        +---------------------+          |
+--------------------------------------------------------------------------------------------------+
```

---

## 2. Configured Services

### 1. `postgres` (Relational Storage)
- **Image**: `postgres:16-alpine`
- **Port**: `5432:5432`
- **Databases**:
  - `fraud_risk`: Raw transaction and identity data tables (`transactions_raw`, `identity_raw`).
  - `airflow`: Dedicated metadata database for Apache Airflow.
- **User**: `fraud_user`
- **Persistent Volume**: `postgres_data:/var/lib/postgresql/data` (ensures transactional data and Airflow run/user states persist across container rebuilds).
- **Health Check**: `pg_isready -U fraud_user -d fraud_risk`

### 2. `redis` (Low-Latency Online Feature Store)
- **Image**: `redis:7-alpine`
- **Port**: `6379:6379`
- **Persistent Volume**: `redis_data:/data`
- **Health Check**: `redis-cli ping`

### 3. `mlflow` (Experiment Tracking & Model Registry Server)
- **Dockerfile**: `docker/Dockerfile.mlflow` (Python 3.12 with `mlflow==3.15.1`)
- **Port**: `5000:5000`
- **Backend Store**: `sqlite:////mlflow/mlflow.db` (bind-mounted from `./mlflow.db`)
- **Artifacts Root**: `/mlflow/artifacts` (bind-mounted from `./mlruns`)
- **Allowed Hosts**: Configured with `--allowed-hosts "*"` to permit cross-service REST communication from `airflow` and `api` within `risk_network`.
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

### 5. `airflow` (ML Pipeline Orchestration & Monitoring)
- **Dockerfile**: `docker/Dockerfile.airflow` (Apache Airflow 2.9.3 with Python 3.12, XGBoost, LightGBM, Optuna, SHAP, and Evidently AI)
- **Port**: `8080:8080`
- **Metadata Database**: Connected to PostgreSQL:
  `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/airflow`
- **Executor**: `LocalExecutor` (enables true parallel task execution, avoiding SQLite table locking).
- **Process Isolation**: `AIRFLOW__CORE__EXECUTE_TASKS_NEW_PYTHON_INTERPRETER=True` (executes tasks in a clean Python subprocess to prevent `fork()` deadlocks with OpenMP/XGBoost).
- **Automated Self-Healing Boot**:
  On startup, the container executes an inlined command that:
  1. Cleans stale `.pid` files (`rm -f /opt/airflow/*.pid`).
  2. Migrates the database schema (`airflow db migrate`).
  3. Guarantees the `admin` user exists with password `admin` (`airflow users create ... || airflow users reset-password ...`).
  4. Pre-populates `standalone_admin_password.txt` with `admin` to prevent random password generation.
  5. Launches `airflow standalone`.
- **Web UI Credentials**: Username: `admin` | Password: `admin`
- **Health Check**: `curl -f http://localhost:8080/health`

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

# Apache Airflow Health
curl http://localhost:8080/health

# Web Dashboards (open in browser)
# FastAPI UI: http://localhost:8000/ui
# MLflow UI:  http://localhost:5000
# Airflow UI: http://localhost:8080 (admin / admin)
```

### 3.6 Stop Services
```powershell
# Stop containers
docker compose stop

# Stop and remove containers and networks (preserves persistent volumes)
docker compose down
```
