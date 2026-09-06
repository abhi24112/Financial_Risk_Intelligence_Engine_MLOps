# Apache Airflow Pipeline Orchestration — Adaptive Financial Risk Intelligence Engine

## 1. Overview & Architecture

**Apache Airflow** serves as the production orchestrator for the Adaptive Financial Risk Intelligence Engine. It manages scheduled and event-driven execution of the complete ML lifecycle, adhering strictly to the **class-based pipeline design** defined in Section 8 of `GEMINI.md`.

```
========================================================================================
DAG 1: financial_risk_training_pipeline (Schedule: @weekly | 0 0 * * 0)
========================================================================================
[ingest_raw_data] ➔ [validate_raw_data] ➔ [clean_transactions] ➔ [engineer_features]
                                                                         |
[register_champion] 🠔 [evaluate_model] 🠔 [train_model] 🠔 [build_datasets] 🠔-+

========================================================================================
DAG 2: financial_risk_drift_monitoring (Schedule: @daily | 0 2 * * *)
========================================================================================
[check_data_drift] ➔ [evaluate_drift_trigger] ➔ Branch:
                                                 ├──> [trigger_automated_retraining]
                                                 └──> [drift_safe_completion]
```

---

## 2. DAG Specifications

### DAG 1: `financial_risk_training_pipeline`
- **File**: [`airflow/dags/financial_risk_training_dag.py`](../../airflow/dags/financial_risk_training_dag.py)
- **Config**: Defined in [`configs/airflow.yaml`](../../configs/airflow.yaml) (`training_dag`)
- **Schedule**: Every Sunday at midnight UTC (`0 0 * * 0`)
- **Key Quality Guardrail**: If `validate_raw_data` fails (e.g. missing primary keys, corrupt schema), it raises an `AirflowException` and **immediately stops downstream training**.

| Stage | Task ID | Pipeline Class | Key Responsibility & Artifact |
| :--- | :--- | :--- | :--- |
| **1. Ingest** | `ingest_raw_data` | `IngestionPipeline` | Load raw CSVs into PostgreSQL raw tables. |
| **2. Validate** | `validate_raw_data` | `ValidationPipeline` | Assert schema integrity, PK uniqueness, downcast types. |
| **3. Clean** | `clean_transactions` | `CleaningPipeline` | Impute missing values, export `dataset/interim/cleaned.parquet`. |
| **4. Feature Eng.** | `engineer_features` | `FeatureEngineeringPipeline` | Compute velocity/behavioral features ➔ `dataset/processed/features.parquet`. |
| **5. Data Split** | `build_datasets` | `DatasetBuilderPipeline` | Group-aware `StratifiedGroupKFold` split (`train/val/test.parquet`). |
| **6. Train** | `train_model` | `TrainingPipeline` | Train XGBoost/LightGBM model and log run parameters to MLflow. |
| **7. Evaluate** | `evaluate_model` | `EvaluationPipeline` | Compute PR-AUC, ROC-AUC, Recall metrics on test split. |
| **8. Register** | `register_champion` | `RegistrationPipeline` | Compare challenger vs. champion PR-AUC; promote winner to `models/production_model.skops`. |

---

### DAG 2: `financial_risk_drift_monitoring`
- **File**: [`airflow/dags/financial_risk_monitoring_dag.py`](../../airflow/dags/financial_risk_monitoring_dag.py)
- **Config**: Defined in [`configs/airflow.yaml`](../../configs/airflow.yaml) (`monitoring_dag`)
- **Schedule**: Daily at 2:00 AM UTC (`0 2 * * *`)
- **Logic**:
  1. Executes `MonitoringPipeline` with **Evidently AI** across reference and current datasets.
  2. `evaluate_drift_trigger` checks if drifted feature share exceeds the threshold (`0.30`).
  3. If drift is detected, branches to `trigger_automated_retraining` (`RetrainingPipeline`), triggering an automated retraining showdown.

---

## 3. Configuration (`configs/airflow.yaml`)

```yaml
training_dag:
  dag_id: "financial_risk_training_pipeline"
  schedule_interval: "0 0 * * 0"
  catchup: false
  max_active_runs: 1
  default_args:
    owner: "mlops_team"
    retries: 2
    retry_delay_seconds: 180

monitoring_dag:
  dag_id: "financial_risk_drift_monitoring"
  schedule_interval: "0 2 * * *"
  catchup: false
  max_active_runs: 1
  default_args:
    owner: "mlops_team"
    retries: 1
    retry_delay_seconds: 120
```

---

## 4. Containerized Architecture & Production Hardening

In production, Apache Airflow runs containerized within the shared Docker network (`risk_network`) as `risk_engine_airflow`. The setup incorporates critical engineering guardrails:

### 4.1 PostgreSQL Metadata Backend & State Persistence
- **Connection**: `postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/airflow`
- **Volume**: Rooted in the Docker-managed `postgres_data` volume.
- **Why this matters**: Moving off ephemeral SQLite ensures that all DAG run histories, task execution logs, user sessions, and connection parameters persist across container rebuilds and restarts.

### 4.2 Process Isolation for ML Workloads (`LocalExecutor`)
- **Setting**: `AIRFLOW__CORE__EXECUTE_TASKS_NEW_PYTHON_INTERPRETER=True`
- **Why this matters**: Standard Airflow task runners use `os.fork()` to spin up execution processes. High-performance machine learning packages (XGBoost, LightGBM, OpenMP) frequently deadlock or crash with `return code 1` when invoked inside forked parent processes, leading to false "Detected zombie job" failures. Forcing a fresh Python interpreter per task provides full process isolation.

### 4.3 Centralized MLflow Tracking
- **Tracking URI**: `http://mlflow:5000` (auto-detected from container environment variable `MLFLOW_TRACKING_URI`).
- **Security / DNS**: The MLflow container is launched with `--allowed-hosts "*"` to support internal Docker DNS resolution without triggering MLflow 3.x DNS-rebinding 403 Forbidden rejections.
- **Artifacts**: All experiments and models trained inside Airflow DAGs are automatically registered and browsable via the central MLflow UI.

### 4.4 Logging Architecture & StreamHandler Protection
- To prevent infinite recursion (`RecursionError: maximum recursion depth exceeded`), pipelines avoid attaching duplicate `StreamHandler(sys.stdout)` handlers when executed inside Airflow's custom `StreamLogWriter` environment. Airflow handles capturing standard stdout and formatting task logs natively.

---

## 5. Operational Runbook

### 5.1 Launch Full Multi-Container Stack (Including Airflow)
```powershell
# Build and start all 5 services in background
docker compose up -d
```

### 5.2 Access Web UIs & Authentication
- **Apache Airflow UI**: [http://localhost:8080](http://localhost:8080)
  - **Username**: `admin`
  - **Password**: `admin`
- **FastAPI Serving & Dashboard**: [http://localhost:8000/ui](http://localhost:8000/ui)
- **MLflow Tracking Server**: [http://localhost:5000](http://localhost:5000)

### 5.3 Trigger DAGs via Airflow CLI
```powershell
# Trigger the training pipeline manually
docker compose exec airflow airflow dags trigger financial_risk_training_pipeline

# Trigger the drift monitoring pipeline manually
docker compose exec airflow airflow dags trigger financial_risk_drift_monitoring

# List all active DAGs
docker compose exec airflow airflow dags list

# Verify configured users
docker compose exec airflow airflow users list
```
