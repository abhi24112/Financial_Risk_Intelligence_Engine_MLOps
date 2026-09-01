# GEMINI.md — Adaptive Financial Risk Intelligence Engine

> Context file for Antigravity. Read this fully before generating or editing any
> code in this repo. It defines what the project is, why it exists, the
> architecture we've committed to, and the coding conventions (especially the
> class-based pipeline pattern) that every module must follow.

---

# Important
- Use the conda environment first before running any code or tests
- Env: financial_risk_intelligence
- command: conda activate financial_risk_intelligence

## 1. What This Project Is

A **production-grade ML Engineering / MLOps project**, not a full-stack product
and not a notebook-style data science project. Built by one developer in
~1–1.5 months as a flagship resume/portfolio project that a fintech company
could plausibly run internally.

**It is explicitly NOT:**
- A fraud detection project (fraud is a downstream signal, not the goal)
- A simple anomaly detection model
- A credit score predictor
- A collection of unrelated notebooks/experiments

**It IS:** a system that continuously evaluates the risk of financial
transactions in production, end-to-end — ingest → validate → engineer
features → train → calibrate → explain → serve → monitor → retrain.

The engineering (deployment, monitoring, automation, reproducibility,
explainability infrastructure) matters more than squeezing out extra model
accuracy or adding more models/datasets. Architectural quality and MLOps
depth are prioritized over model count or dataset count.

---

## 2. What The System Does (Functional Requirements)

For every incoming transaction, the system:
1. Calculates a **risk score** (0–100) **within a strict <100ms latency SLA**
2. Assigns a **risk level** (Low / Medium / High)
3. Classifies **Anomalous vs Normal**
4. **Explains why** the transaction was flagged — using SHAP-driven,
   analyst-readable reasons, not hardcoded strings
5. **Logs** the prediction and metadata
6. Is continuously **monitored** for performance and drift
7. **Detects data drift** (and model drift where feasible)
8. **Triggers retraining** automatically when needed
9. **Versions** datasets and models
10. Serves everything through **production REST APIs**

---

## 3. Datasets

Two datasets appear across the source docs — **be aware both exist, but they
are not used the same way in this repo:**

- **Primary / actually adopted dataset: IEEE-CIS Fraud Detection (Kaggle).**
  This is what the current architecture, feature IV analysis, database name
  (`fraud_risk`), and folder layout are built around. Joined on
  `TransactionID` across `transaction` and `identity` files.
- **Originally proposed / conceptual foundation: Berka / PKDD'99 Czech Bank
  dataset.** Multi-table relational data (clients, accounts, transactions,
  loans, cards, districts) — this was the original plan for realistic
  relational feature engineering but the project pivoted to IEEE-CIS as the
  actual V1 dataset.
- Optional future enrichment (not built yet, only additive if it earns its
  place): **Transactions Fraud Dataset (computingvictor)** for extra
  customer/card/behavioral relationships.

**Rule: do not silently merge datasets.** Any new dataset must solve a
specific, named business/technical problem and must not require rearchitecting
the ingestion pipeline. New sources plug in through `ingestion_pipeline`
only.

### IEEE-CIS specifics worth remembering
- Target: `isFraud` (binary)
- Join key: `TransactionID`
- `TransactionDT` is a **timedelta from a reference point, not a real
  timestamp** — don't treat it as wall-clock time.
- Feature triage already done (see `docs/feature_selection.md` once written):
  - **Drop:** `card4`, `M1`, `M7`, `M8`, `R_emaildomain` (leaks 0.0 fraud
    rate across all domains), `C3`, `id_10`, `id_11`, `id_12`, `id_13`,
    `id_37` (IV ≈ 0, noise)
  - **Strong (IV 0.3–0.5):** `card3`, `M4`, `ProductCD`
  - **Medium (IV 0.1–0.3):** `TransactionAmt`, `card6`, `P_emaildomain`,
    `DeviceInfo`
  - **Weak but useful (IV 0.02–0.1):** `card1`, `card2`, `card5`, `dist1`,
    `dist2`, `DeviceType`, `M2`, `M3`, `M5`, `M6`, `M9`
  - **Special case — `addr1`/`addr2`:** low IV as raw categoricals, but
    NaNs are disproportionately fraud-heavy (~37%). Don't drop; extract an
    `is_missing` flag instead of expecting the raw code to help.
  - Full `V*`, `C*`, `D*`, `id_*` retained lists live in the source roadmap
    doc — feature_store code should read this list from config, not
    hardcode it inline.

---

## 4. Core ML Components

### 4.1 Transaction Risk Engine (primary model)
Inputs: transaction amount, merchant/product code, customer history,
time, device/identity fields (where available), engineered behavioral
aggregates.
Output: risk score (0–100), risk level (Low/Med/High), anomalous/normal flag.

### 4.2 Explainability Engine
- Must use **real explainability (SHAP)**, not hardcoded if/else reason
  strings.
- **Hard architectural rule: prediction and explanation are separate
  components.** The model may use all features, including anonymized
  `V`/`C`/`D` columns. Business-facing explanations must only reference
  **interpretable, engineered features** — never raw anonymized columns.
- Output should read like something a fraud/risk analyst would actually see,
  e.g. "Transaction amount is 4.2x the customer's 90-day average" — not
  "V187 contributed +0.31 to SHAP value."

---

## 5. Architecture Decisions (already made — don't relitigate without reason)

- **Latency SLA:** The `/predict` API must return a score in <100ms. To achieve this, it relies on an Online Feature Store (Redis) for O(1) feature lookups, bypassing PostgreSQL during inference.
- IEEE-CIS only for V1; future datasets are additive, not required.
- Model may see all features; explanations may not.
- **Decoupled Explainability:** SHAP computation is too slow for the 100ms SLA. Prediction and explanation are hard-decoupled. The `/predict` endpoint returns instantly; the `/explain` endpoint runs separately (or async).
- **Champion/Challenger** model promotion strategy for retraining, not blind
  auto-replace.
- Data drift monitoring (Evidently AI) triggers retraining; retraining is not
  purely time-scheduled.
- Group-aware validation: use **GroupKFold / StratifiedGroupKFold** so a
  single customer's transactions don't leak across train/val splits.
- Metric priorities: **recall-first** (catch fraud), Fβ-score with β > 1,
  cost-sensitive class weighting — this is an imbalanced classification
  problem and should be evaluated as one (ROC-AUC, PR-AUC, F1, confusion
  matrix — not raw accuracy).
- Risk score ≠ raw model probability. Calibrate (Platt scaling or isotonic
  regression) before turning probability into a 0–100 risk score.

---

## 6. Technology Stack (only use what has a real purpose here)

| Layer | Tech | Purpose |
|---|---|---|
| Modeling | Python, Scikit-learn, XGBoost/LightGBM | training, baseline + tuned models |
| Explainability | SHAP | prediction-level and global explanations |
| Experiment tracking / registry | MLflow | runs, params, metrics, model registry, champion/challenger |
| Data versioning | DVC | raw/interim/processed dataset versioning |
| Orchestration | Airflow | DAG: validate → feature engineer → train → evaluate → register |
| Serving | FastAPI | `/predict`, `/explain`, `/health`, `/metrics` |
| Storage | PostgreSQL | transactional/history data, feature history |
| Cache | Redis | low-latency feature/prediction serving |
| Monitoring | Evidently AI | data drift, prediction drift, feature distribution |
| Containerization | Docker, Docker Compose | local + prod parity |
| Orchestrated deploy | AWS ECS (Fargate) or EKS | serving at scale with low latency |
| IaC | Terraform | AWS resources (ECS/EKS, ElastiCache Redis, RDS, VPC) |
| Streaming | **None (No Kafka)** | Intentional exclusion. We rely on **FastAPI's `asyncio` concurrency + horizontal scaling behind a Load Balancer** to handle thousands of simultaneous requests. This meets our synchronous <100ms REST SLA without over-engineering an asynchronous Pub/Sub queue. |
| CI/CD | GitHub Actions | test → build → push image → deploy |

**Rule:** don't add a technology unless it maps to a concrete need above.
Anything speculative goes in `docs/roadmap.md` as "future," not into the repo.

---

## 7. Repository Layout (top-level, already fixed — do not restructure casually)

```
Adaptive-Financial-Risk-Intelligence-Engine/
├── .github/            # CI/CD workflows, issue/PR templates, CODEOWNERS
├── airflow/            # dags/, plugins/, operators/, sensors/
├── api/                # FastAPI: routes/, middleware/, schemas.py, app.py, main.py
├── apps/                # service entrypoints (inference_service.py, monitoring_service.py, ...)
├── configs/             # model.yaml, airflow.yaml, database.yaml, api.yaml, monitoring.yaml, logging.yaml, aws.yaml, paths.yaml — NO hardcoded values anywhere else
├── data/                 # raw/, interim/, processed/, external/, validation_reports/ — DVC-tracked, local/temp only
├── database/             # connection.py, loader.py, schema.py, queries.py, session.py, migrations/ — DB interaction ONLY, no ML logic
├── deployment/            # docker/, kubernetes/, aws/, scripts/
├── docker/                # Dockerfile.api, Dockerfile.training, Dockerfile.airflow, entrypoint.sh
├── docs/                   # architecture.md, api.md, ml_pipeline.md, deployment.md, roadmap.md, interview_notes.md
├── dvc/                     # pipelines/, stages/, params.yaml
├── explainability/           # shap_engine.py, analyst_view.py, debug_view.py, feature_mapper.py, templates.py, explanation_service.py
├── feature_store/              # feature_builder.py, feature_registry.py, aggregations.py, validators.py, metadata.py
├── infrastructure/               # terraform/, aws/, networking/, variables/
├── ml/                             # training/, inference/, evaluation/, calibration/, registry/, models/, utils/
├── monitoring/                      # evidently/, metrics.py, drift.py, alerts.py, dashboards.py
├── pipelines/                        # <-- see Section 8, this is the ML lifecycle backbone
├── scripts/                            # CLI helpers: download_dataset.py, seed_database.py, train.py, predict.py, explain.py, cleanup.py
├── shared/                              # logger.py, constants.py, exceptions.py, decorators.py, helpers.py, enums.py
├── tests/                                # unit/, integration/, api/, ml/, performance/
├── notebooks/                             # exploration ONLY — 01_eda.ipynb, 02_feature_engineering.ipynb, 03_model_experiments.ipynb, archive/ — NO production code lives here
├── docker-compose.yml                     # runs PostgreSQL, Redis, MLflow, Airflow, API
├── pyproject.toml
├── requirements.txt
├── README.md
└── Makefile                                # make train / make api / make airflow / make test / make lint / make deploy
```

---

## 8. Pipelines — Class-Based Design (this is the part not fully in the source docs)

This section formalizes something implied but not explicitly written out in
the original planning docs: **every pipeline is a class, not a loose script**,
so Airflow integration, testing, and logging are consistent everywhere.

### 8.1 Core convention

- `pipelines/base_pipeline.py` defines an **abstract `BasePipeline`** that
  every concrete pipeline inherits from.
- Every concrete pipeline lives in its own file, is a class, and exposes a
  single public **`run()`** method as its entrypoint. Airflow tasks call
  `SomePipeline(config).run()` — nothing else.
- `BasePipeline` owns the parts that are identical across all 14 stages so
  they aren't duplicated 14 times:
  - structured logging (via `shared/logger.py`)
  - config loading (via `configs/*.yaml`, no hardcoded values)
  - timing / duration tracking
  - exception handling + consistent error reporting
  - artifact tracking (what files/objects this run produced)
  - status reporting (success/failure/skipped, written somewhere Airflow
    and monitoring can read)
- Concrete pipelines implement **only their own business logic**, typically
  by overriding a protected method (e.g. `_execute()`) that `run()` calls
  internally after setup and before teardown.

### 8.2 Reference shape

```python
# pipelines/base_pipeline.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from shared.logger import get_logger
from shared.exceptions import PipelineError


@dataclass
class PipelineResult:
    pipeline_name: str
    status: str  # "success" | "failed" | "skipped"
    started_at: datetime
    finished_at: datetime | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class BasePipeline(ABC):
    """
    Shared lifecycle for every stage of the ML system.
    Concrete pipelines implement `_execute()`; `run()` is the only
    method Airflow / scripts / other pipelines should call.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
        self.name = self.__class__.__name__

    @abstractmethod
    def _execute(self) -> dict[str, Any]:
        """Business logic for this specific pipeline stage.
        Returns a dict of artifacts/metadata to attach to PipelineResult."""
        raise NotImplementedError

    def run(self) -> PipelineResult:
        started_at = datetime.utcnow()
        self.logger.info(f"[{self.name}] starting")
        try:
            output = self._execute()
            result = PipelineResult(
                pipeline_name=self.name,
                status="success",
                started_at=started_at,
                finished_at=datetime.utcnow(),
                artifacts=output.get("artifacts", {}),
                metadata=output.get("metadata", {}),
            )
            self.logger.info(f"[{self.name}] completed successfully")
            return result
        except Exception as exc:  # noqa: BLE001 - intentional top-level boundary
            self.logger.exception(f"[{self.name}] failed")
            return PipelineResult(
                pipeline_name=self.name,
                status="failed",
                started_at=started_at,
                finished_at=datetime.utcnow(),
                error=str(exc),
            )
```

```python
# pipelines/ingestion_pipeline.py
from pipelines.base_pipeline import BasePipeline
from database.loader import CSVLoader
from database.connection import Database


class IngestionPipeline(BasePipeline):
    """Move raw CSVs into PostgreSQL as transactions_raw / identity_raw."""

    def _execute(self) -> dict:
        db = Database(self.config["database"])
        loader = CSVLoader(self.config["paths"]["raw_data"])

        loader.load_transactions(db, table="transactions_raw")
        loader.load_identity(db, table="identity_raw")

        return {
            "artifacts": {"tables": ["transactions_raw", "identity_raw"]},
            "metadata": {"rows_loaded": loader.total_rows_loaded},
        }
```

### 8.3 The 14 pipeline classes (one file, one class, one responsibility each)

| File | Class | Responsibility | Key output |
|---|---|---|---|
| `ingestion_pipeline.py` | `IngestionPipeline` | CSV → PostgreSQL | `transactions_raw`, `identity_raw` |
| `validation_pipeline.py` | `ValidationPipeline` | schema/null/dupe/type checks; **stops the DAG on failure** | `validation_report.json` |
| `cleaning_pipeline.py` | `CleaningPipeline` | fill/convert/normalize; DB stays untouched | `cleaned.parquet` |
| `feature_engineering_pipeline.py` | `FeatureEngineeringPipeline` | time/amount/email/device/behavioral features | `features.parquet` |
| `dataset_builder_pipeline.py` | `DatasetBuilderPipeline` | split (group-aware), encode, scale, sample | `train/validation/test.parquet` |
| `training_pipeline.py` | `TrainingPipeline` | train XGBoost/LightGBM, tune, log to MLflow | `model.pkl` |
| `evaluation_pipeline.py` | `EvaluationPipeline` | ROC-AUC, PR-AUC, F1, recall, confusion matrix | `evaluation.json` |
| `calibration_pipeline.py` | `CalibrationPipeline` | Platt/isotonic calibration of probabilities | `calibrated_model.pkl` |
| `registration_pipeline.py` | `RegistrationPipeline` | champion/challenger compare, register, promote | MLflow Model Registry entry |
| `inference_pipeline.py` | `InferencePipeline` | new transaction → features → model → risk score | prediction object |
| `explainability_pipeline.py` | `ExplainabilityPipeline` | SHAP → analyst view → business explanation | `{risk_score, reasons, confidence, model_version}` |
| `monitoring_pipeline.py` | `MonitoringPipeline` | data/prediction drift, feature distribution, live metrics (via Evidently) | drift/monitoring reports |
| `retraining_pipeline.py` | `RetrainingPipeline` | scheduled or drift-triggered: retrain → evaluate → register → deploy | new registered model |
| `deployment_pipeline.py` | `DeploymentPipeline` | build image, push, deploy API, update K8s | deployed service |

Pipeline dependency order (this is the Airflow DAG shape):

```
Ingestion → Validation → Cleaning → Feature Engineering → Dataset Builder
→ Training → Evaluation → Calibration → Registration → Deployment
→ Inference → Explainability → Monitoring → Retraining
```

`training_pipeline.py` (DAG-level Airflow orchestration) covers
Validate → Feature Engineering → Train → Evaluate → Register.
`retraining_pipeline.py` reuses the same classes rather than duplicating
logic — it's a re-invocation of the training path triggered by
`monitoring_pipeline.py` detecting drift, or by a schedule.

### 8.4 Rules for every pipeline class
- One class per file, file name matches class name in snake_case.
- No business logic inside `__init__` — only wiring/config. All real work
  happens in `_execute()`, called only via `run()`.
- No pipeline reaches into another pipeline's internals — they communicate
  only through their declared outputs (files in `data/`, models in the
**Rule:** don't add a technology unless it maps to a concrete need above.
Anything speculative goes in `docs/roadmap.md` as "future," not into the repo.

---

## 7. Repository Layout (top-level, already fixed — do not restructure casually)

```
Adaptive-Financial-Risk-Intelligence-Engine/
├── .github/            # CI/CD workflows, issue/PR templates, CODEOWNERS
├── airflow/            # dags/, plugins/, operators/, sensors/
├── api/                # FastAPI: routes/, middleware/, schemas.py, app.py, main.py
├── apps/                # service entrypoints (inference_service.py, monitoring_service.py, ...)
├── configs/             # model.yaml, airflow.yaml, database.yaml, api.yaml, monitoring.yaml, logging.yaml, aws.yaml, paths.yaml — NO hardcoded values anywhere else
├── data/                 # raw/, interim/, processed/, external/, validation_reports/ — DVC-tracked, local/temp only
├── database/             # connection.py, loader.py, schema.py, queries.py, session.py, migrations/ — DB interaction ONLY, no ML logic
├── deployment/            # docker/, kubernetes/, aws/, scripts/
├── docker/                # Dockerfile.api, Dockerfile.training, Dockerfile.airflow, entrypoint.sh
├── docs/                   # architecture.md, api.md, ml_pipeline.md, deployment.md, roadmap.md, interview_notes.md
├── dvc/                     # pipelines/, stages/, params.yaml
├── explainability/           # shap_engine.py, analyst_view.py, debug_view.py, feature_mapper.py, templates.py, explanation_service.py
├── feature_store/              # feature_builder.py, feature_registry.py, aggregations.py, validators.py, metadata.py
├── infrastructure/               # terraform/, aws/, networking/, variables/
├── ml/                             # training/, inference/, evaluation/, calibration/, registry/, models/, utils/
├── monitoring/                      # evidently/, metrics.py, drift.py, alerts.py, dashboards.py
├── pipelines/                        # <-- see Section 8, this is the ML lifecycle backbone
├── scripts/                            # CLI helpers: download_dataset.py, seed_database.py, train.py, predict.py, explain.py, cleanup.py
├── shared/                              # logger.py, constants.py, exceptions.py, decorators.py, helpers.py, enums.py
├── tests/                                # unit/, integration/, api/, ml/, performance/
├── notebooks/                             # exploration ONLY — 01_eda.ipynb, 02_feature_engineering.ipynb, 03_model_experiments.ipynb, archive/ — NO production code lives here
├── docker-compose.yml                     # runs PostgreSQL, Redis, MLflow, Airflow, API
├── pyproject.toml
├── requirements.txt
├── README.md
└── Makefile                                # make train / make api / make airflow / make test / make lint / make deploy
```

---

## 8. Pipelines — Class-Based Design (this is the part not fully in the source docs)

This section formalizes something implied but not explicitly written out in
the original planning docs: **every pipeline is a class, not a loose script**,
so Airflow integration, testing, and logging are consistent everywhere.

### 8.1 Core convention

- `pipelines/base_pipeline.py` defines an **abstract `BasePipeline`** that
  every concrete pipeline inherits from.
- Every concrete pipeline lives in its own file, is a class, and exposes a
  single public **`run()`** method as its entrypoint. Airflow tasks call
  `SomePipeline(config).run()` — nothing else.
- `BasePipeline` owns the parts that are identical across all 14 stages so
  they aren't duplicated 14 times:
  - structured logging (via `shared/logger.py`)
  - config loading (via `configs/*.yaml`, no hardcoded values)
  - timing / duration tracking
  - exception handling + consistent error reporting
  - artifact tracking (what files/objects this run produced)
  - status reporting (success/failure/skipped, written somewhere Airflow
    and monitoring can read)
- Concrete pipelines implement **only their own business logic**, typically
  by overriding a protected method (e.g. `_execute()`) that `run()` calls
  internally after setup and before teardown.

### 8.2 Reference shape

```python
# pipelines/base_pipeline.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from shared.logger import get_logger
from shared.exceptions import PipelineError


@dataclass
class PipelineResult:
    pipeline_name: str
    status: str  # "success" | "failed" | "skipped"
    started_at: datetime
    finished_at: datetime | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class BasePipeline(ABC):
    """
    Shared lifecycle for every stage of the ML system.
    Concrete pipelines implement `_execute()`; `run()` is the only
    method Airflow / scripts / other pipelines should call.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
        self.name = self.__class__.__name__

    @abstractmethod
    def _execute(self) -> dict[str, Any]:
        """Business logic for this specific pipeline stage.
        Returns a dict of artifacts/metadata to attach to PipelineResult."""
        raise NotImplementedError

    def run(self) -> PipelineResult:
        started_at = datetime.utcnow()
        self.logger.info(f"[{self.name}] starting")
        try:
            output = self._execute()
            result = PipelineResult(
                pipeline_name=self.name,
                status="success",
                started_at=started_at,
                finished_at=datetime.utcnow(),
                artifacts=output.get("artifacts", {}),
                metadata=output.get("metadata", {}),
            )
            self.logger.info(f"[{self.name}] completed successfully")
            return result
        except Exception as exc:  # noqa: BLE001 - intentional top-level boundary
            self.logger.exception(f"[{self.name}] failed")
            return PipelineResult(
                pipeline_name=self.name,
                status="failed",
                started_at=started_at,
                finished_at=datetime.utcnow(),
                error=str(exc),
            )
```

```python
# pipelines/ingestion_pipeline.py
from pipelines.base_pipeline import BasePipeline
from database.loader import CSVLoader
from database.connection import Database


class IngestionPipeline(BasePipeline):
    """Move raw CSVs into PostgreSQL as transactions_raw / identity_raw."""

    def _execute(self) -> dict:
        db = Database(self.config["database"])
        loader = CSVLoader(self.config["paths"]["raw_data"])

        loader.load_transactions(db, table="transactions_raw")
        loader.load_identity(db, table="identity_raw")

        return {
            "artifacts": {"tables": ["transactions_raw", "identity_raw"]},
            "metadata": {"rows_loaded": loader.total_rows_loaded},
        }
```

### 8.3 The 14 pipeline classes (one file, one class, one responsibility each)

| File | Class | Responsibility | Key output |
|---|---|---|---|
| `ingestion_pipeline.py` | `IngestionPipeline` | CSV → PostgreSQL | `transactions_raw`, `identity_raw` |
| `validation_pipeline.py` | `ValidationPipeline` | schema/null/dupe/type checks; **stops the DAG on failure** | `validation_report.json` |
| `cleaning_pipeline.py` | `CleaningPipeline` | fill/convert/normalize; DB stays untouched | `cleaned.parquet` |
| `feature_engineering_pipeline.py` | `FeatureEngineeringPipeline` | time/amount/email/device/behavioral features | `features.parquet` |
| `dataset_builder_pipeline.py` | `DatasetBuilderPipeline` | split (group-aware), encode, scale, sample | `train/validation/test.parquet` |
| `training_pipeline.py` | `TrainingPipeline` | train XGBoost/LightGBM, tune, log to MLflow | `model.pkl` |
| `evaluation_pipeline.py` | `EvaluationPipeline` | ROC-AUC, PR-AUC, F1, recall, confusion matrix | `evaluation.json` |
| `calibration_pipeline.py` | `CalibrationPipeline` | Platt/isotonic calibration of probabilities | `calibrated_model.pkl` |
| `registration_pipeline.py` | `RegistrationPipeline` | champion/challenger compare, register, promote | MLflow Model Registry entry |
| `inference_pipeline.py` | `InferencePipeline` | new transaction → features → model → risk score | prediction object |
| `explainability_pipeline.py` | `ExplainabilityPipeline` | SHAP → analyst view → business explanation | `{risk_score, reasons, confidence, model_version}` |
| `monitoring_pipeline.py` | `MonitoringPipeline` | data/prediction drift, feature distribution, live metrics (via Evidently) | drift/monitoring reports |
| `retraining_pipeline.py` | `RetrainingPipeline` | scheduled or drift-triggered: retrain → evaluate → register → deploy | new registered model |
| `deployment_pipeline.py` | `DeploymentPipeline` | build image, push, deploy API, update K8s | deployed service |

Pipeline dependency order (this is the Airflow DAG shape):

```
Ingestion → Validation → Cleaning → Feature Engineering → Dataset Builder
→ Training → Evaluation → Calibration → Registration → Deployment
→ Inference → Explainability → Monitoring → Retraining
```

`training_pipeline.py` (DAG-level Airflow orchestration) covers
Validate → Feature Engineering → Train → Evaluate → Register.
`retraining_pipeline.py` reuses the same classes rather than duplicating
logic — it's a re-invocation of the training path triggered by
`monitoring_pipeline.py` detecting drift, or by a schedule.

### 8.4 Rules for every pipeline class
- One class per file, file name matches class name in snake_case.
- No business logic inside `__init__` — only wiring/config. All real work
  happens in `_execute()`, called only via `run()`.
- No pipeline reaches into another pipeline's internals — they communicate
  only through their declared outputs (files in `data/`, models in the
  registry, reports in `monitoring/`).
- No hardcoded paths, table names, thresholds, or hyperparameters inside
  pipeline classes — everything comes from `configs/*.yaml`.
- Every pipeline must be independently testable: `tests/ml/` and
  `tests/integration/` should be able to instantiate a pipeline with a
  fake/small config and call `.run()` without needing the full stack up.

---

## 9. Logging

`logs/` folder (`application.log`, `api.log`, `training.log`, `airflow.log`,
`monitoring.log`) is written to as we build, not pre-populated. All logging
goes through `shared/logger.py` so format/handlers stay consistent across
pipelines, the API, and Airflow tasks.

---

## 10. Database

- DB name: `fraud_risk`
- User: `fraud_user`
- `database/` package handles all DB interaction — **no ML logic in this
  folder, ever.** Feature computation belongs in `feature_store/` or
  `pipelines/feature_engineering_pipeline.py`, not in `database/`.

*(Note: credentials referenced in the original planning notes are dev-only
placeholders — do not hardcode real credentials in code or config; use
environment variables / secrets management for anything beyond local dev.)*

---

## 11. How I Want Antigravity To Work With Me On This

- Act like a senior ML engineer reviewing/pairing, not a yes-man. Push back
  on scope creep, unnecessary tech, or anything that turns this into a
  notebook project.
- When introducing anything new, briefly justify: why it exists, what
  problem it solves, whether it's realistic for production, whether it's
  worth it for resume value, or whether it's unneeded complexity.
- Favor one exceptional, coherent system over several average or bolted-on
  pieces.
- Keep the pipeline-as-class convention (Section 8) consistent everywhere —
  if a new pipeline stage is ever added, it must inherit `BasePipeline` and
  follow the same `run()`/`_execute()` shape.

---


## 12. Project Status & Progress Tracker

This section lists the implemented tasks and what needs to be worked on next, so new chats or other agents can seamlessly pick up the context.

### Current Progress

1. **Database Setup**: ✅ Complete. Raw transactions loaded into PostgreSQL (`fraud_risk` DB, user `fraud_user`).

2. **Ingestion Pipeline (`pipelines/ingestion_pipeline.py`)**: ✅ Complete.
   - Loads raw CSVs into PostgreSQL. Verified working.

3. **Validation & Cleaning Pipelines**: ✅ Complete.
   - Schema checks, downcasting, column dropping (retaining `SELECTED_FEATURES_TO_KEEP`), and missing value imputation done.

4. **Feature Engineering & Dataset Builder**: ✅ Complete.
   - Engineered behavioral features and successfully built `train.parquet`, `val.parquet`, and `test.parquet` using `StratifiedGroupKFold` to prevent user leakage.

5. **Training Pipeline (`pipelines/training_pipeline.py`)**: ✅ Complete.
   - Implemented `ModelTrainer` supporting XGBoost, LightGBM, and Random Forest.
   - Integrates deeply with MLflow (`sqlite:///mlflow.db`) to track all parameters.
   - Fixes LightGBM `skops_trusted_types` issues.

6. **Evaluation Pipeline (`pipelines/evaluation_pipeline.py`)**: ✅ Complete.
   - Dynamically reads `run_id` from the training report, predicts on the test set, and logs business metrics (PR-AUC, Recall, F1, Confusion Matrix) *into the exact same MLflow run*.

7. **Experimentation & Tuning Scripts**: ✅ Complete.
   - `scripts/run_experiments.py`: Loops over all baselines and ranks them by PR-AUC.
   - `scripts/tune.py`: Uses **Optuna** to independently hyperparameter-tune XGBoost, LightGBM, and Random Forest with clean `tqdm` progress bars.

8. **Registration Pipeline (`pipelines/registration_pipeline.py`)**: ✅ Complete.
   - Implements Champion/Challenger promotion showdown in MLflow Model Registry based on PR-AUC.

9. **Serving Layer & Explainability (`api/`)**: ✅ Complete.
   - High-throughput FastAPI app meeting strict <100ms latency SLA.
   - Lifespan (`@asynccontextmanager`) in-memory model loading and Redis pool warming.
   - Pydantic V2 data contracts (`api/schemas.py`) for single & vectorized batch requests.
   - `RequestTimingAndIDMiddleware` injecting `X-Request-ID` and `X-Response-Time-Ms`.
   - Dedicated `/predict`, `/predict/batch`, `/explain` (SHAP), `/health`, and `/ready` routes.
   - Standalone interactive Web UI Dashboard served at `/ui` with batch throughput telemetry.
   - Zero lint errors (`ruff check` clean) and automated integration tests passing (`tests/integration/test_api.py`).

10. **Monitoring & Drift Detection Pipeline (`pipelines/monitoring_pipeline.py`)**: ✅ Complete.
    - Uses **Evidently AI** (`DataDefinition`, `Dataset.from_pandas`, `DataDriftPreset`) to monitor covariate shift and feature distributions.
    - Generates interactive HTML and programmatic JSON drift reports in `monitoring/reports/`.
    - Evaluates `drift_share` against threshold (`configs/monitoring.yaml`) to output automated retraining triggers.

11. **Retraining Pipeline (`pipelines/retraining_pipeline.py`)**: ✅ Complete.
    - Orchestrates end-to-end retraining flow: [Drift Check] ➔ [Train Challenger] ➔ [Evaluate Metrics] ➔ [Champion vs. Challenger Showdown].
    - Reuses existing pipeline classes cleanly without code duplication.

12. **Data Versioning & Pipeline Lineage (`dvc.yaml`, `params.yaml`)**: ✅ Complete.
    - Initialized DVC tracking with `.dvcignore` excluding caches/logs/db.
    - Defined parameterization knobs in `params.yaml`.
    - Codified reproducible data DAG stages (`cleaning` ➔ `feature_engineering` ➔ `dataset_builder`).
    - Explicitly tracked Champion (`models/production_model.skops`) and Challenger (`models/challenger_model.skops`) model weights alongside Parquet datasets.
    - Configured local remote storage (`../dvc_remote_storage`) and pushed all 7 data and model artifacts (`dvc push`).
    - Verified `dvc status` reports `Data and pipelines are up to date.`

### Running Pipeline Scripts / Tests

Always activate the conda environment and set `PYTHONPATH` before running any script:

```powershell
conda activate financial_risk_intelligence
$env:PYTHONPATH = "."

# View DVC Pipeline DAG
dvc dag

# Check DVC Stage Statuses
dvc status

# Run Monitoring Pipeline
python pipelines/monitoring_pipeline.py

# Run Retraining Pipeline (forced or drift-triggered)
python pipelines/retraining_pipeline.py

# Run API Tests
pytest tests/integration/test_api.py

# Start FastAPI Server
python main.py
```

### Known Issues / Gotchas

- **LightGBM Categorical Error during Inference**: (FIXED) The test inference script previously failed with `ValueError: train and valid dataset categorical_feature do not match.`
  - **The Fix**: Instead of wrestling with Pandas `.astype("category")`, we bypass the validation entirely. We manually hash string categories into numeric codes (`hash(str) % 2**31`), fill missing values with `-1.0`, and pass a pure `float64` numpy array (`df.values`) into `model.predict_proba()`.
- **Async Event Loop Protection**: ML model inference and SHAP calculations are CPU-bound. In FastAPI route handlers, always wrap them in `await asyncio.to_thread(func, *args)` to prevent freezing the single-threaded event loop.
- **Risk Score Calibration**: Fraud prevalence in IEEE-CIS is ~3.5%. Raw probabilities output by tree models are compressed. `InferencePipeline._calculate_calibrated_risk()` maps probabilities relative to the 3.5% baseline into clear 0–100 risk scores (Low: <3.5%, Medium: 3.5–8%, High: >=8%).
- **Do NOT use `SELECT *`** when loading from PostgreSQL in this project — the transaction table has 394 columns and will trigger `ArrayMemoryError` on low-RAM machines.
- **MLflow Tracking Backend**: We use `sqlite:///mlflow.db` because `./mlruns` is deprecated by MLflow for UI usage.

### Next Steps & Tasks

- [ ] **Containerization & Parity (`Dockerfile`, `docker-compose.yml`)**: Package PostgreSQL, Redis, MLflow, FastAPI Serving API, and Airflow into multi-container Docker Compose.
- [ ] **Airflow Orchestration DAG (`airflow/dags/financial_risk_dag.py`)**: Create the production DAG connecting all pipeline classes in sequence (Ingest ➔ Validate ➔ Clean ➔ Engineer ➔ Train ➔ Evaluate ➔ Register).

