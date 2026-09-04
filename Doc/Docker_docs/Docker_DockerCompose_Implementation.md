# Implementation Plan - Docker & Docker Compose Containerization

Containerize the entire **Adaptive Financial Risk Intelligence Engine** stack into a unified, multi-service **Docker Compose** environment providing local & production parity, automatic health checks, isolated networking, and seamless cross-service communication.

## User Review Required

> [!IMPORTANT]
> - **PostgreSQL (`fraud_risk`)** and **Redis** will run as containerized services with persistent volumes.
> - **MLflow Server** will run in a dedicated tracking container exposed on port `5000`.
> - **FastAPI Serving Engine** will run in a lightweight Python 3.11 container exposed on port `8000`.
> - **Apache Airflow** will run with our custom dependencies, mounting `airflow/dags/` and repo code directly to execute pipeline classes seamlessly without Windows OS limitations.

## Services Architecture

```mermaid
graph TD
    subgraph Docker Network [financial-risk-network]
        API["FastAPI Serving & UI<br/>(:8000)"]
        MLFLOW["MLflow Tracking Server<br/>(:5000)"]
        AIRFLOW["Apache Airflow (Scheduler+Webserver)<br/>(:8080)"]
        POSTGRES[("PostgreSQL DB<br/>(:5432)")]
        REDIS[("Redis Feature Store<br/>(:6379)")]
    end

    API --> POSTGRES
    API --> REDIS
    API --> MLFLOW
    AIRFLOW --> POSTGRES
    AIRFLOW --> REDIS
    AIRFLOW --> MLFLOW
```

## Proposed Files to Create & Update

### 1. [NEW] `docker/Dockerfile.api`
- Lightweight Python base (`python:3.11-slim`).
- Installs system dependencies (`curl`, `build-essential`, `libgomp1` for LightGBM/XGBoost).
- Installs Python dependencies from `requirements.txt`.
- Exposes port `8000` and launches Uvicorn server (`main.py`).
- Built-in `HEALTHCHECK` hitting `/health`.

### 2. [NEW] `docker/Dockerfile.airflow`
- Based on `apache/airflow:2.9.2-python3.11`.
- Installs ML pipeline libraries (`xgboost`, `lightgbm`, `optuna`, `evidently`, `shap`, `psycopg2-binary`, `scikit-learn`, `redis`, `mlflow`).
- Sets up `PYTHONPATH=/opt/airflow` and permissions for seamless pipeline execution.

### 3. [NEW] `docker-compose.yml`
Defines 5 coordinated services under a shared bridge network (`risk_net`):
1. **`postgres`**: `postgres:16-alpine`, port `5432:5432`, volume `postgres_data`, healthcheck `pg_isready`.
2. **`redis`**: `redis:7-alpine`, port `6379:6379`, volume `redis_data`, healthcheck `redis-cli ping`.
3. **`mlflow`**: Runs MLflow tracking server on port `5000:5000`, volume `mlflow_data`.
4. **`api`**: Builds `docker/Dockerfile.api`, port `8000:8000`, environment variables (`DATABASE_URL`, `REDIS_URL`, `MLFLOW_TRACKING_URI`), depends on `postgres`, `redis`, `mlflow`.
5. **`airflow`**: Builds `docker/Dockerfile.airflow`, port `8080:8080`, runs Airflow standalone (or webserver + scheduler), mounts `airflow/dags/`, `pipelines/`, `dataset/`, `models/`, `configs/`.

### 4. [NEW] `.env.example` & [MODIFY] `.env`
Defines uniform environment variables:
```env
# Database
POSTGRES_USER=fraud_user
POSTGRES_PASSWORD=admin
POSTGRES_DB=fraud_risk
POSTGRES_PORT=5432
DATABASE_URL=postgresql://fraud_user:admin@postgres:5432/fraud_risk

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_URL=redis://redis:6379/0

# MLflow
MLFLOW_TRACKING_URI=http://mlflow:5000

# Airflow
AIRFLOW__CORE__LOAD_EXAMPLES=False
AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=False
```

### 5. [NEW] `.dockerignore`
Excludes large unneeded local artifacts from build context (`.git`, `.venv`, `dataset/raw`, `.pytest_cache`, `logs/`).

## Verification Plan

### Automated Build & Container Testing
- `docker compose config` to validate YAML syntax and variable substitution.
- `docker compose build` to verify images compile without dependency conflicts.
- `docker compose up -d` to launch all 5 containers in background.
- `docker compose ps` to verify all services reach `healthy` / `running` status.
- Curl tests:
  - `curl http://localhost:8000/health` (FastAPI)
  - `curl http://localhost:5000/health` (MLflow)
  - `curl http://localhost:8080/health` (Airflow)
