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
1. Calculates a **risk score** (0–100)
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

- IEEE-CIS only for V1; future datasets are additive, not required.
- Model may see all features; explanations may not.
- Prediction and explanation are decoupled services/pipelines.
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
| Orchestrated deploy | Kubernetes (kind/minikube locally; optional AWS) | serving at scale |
| IaC | Terraform | AWS resources (S3, ECR, RDS, IAM, networking) |
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

1. **Database Setup**: Completed. Raw transactions loaded into PostgreSQL (`fraud_risk` DB, user `fraud_user`).

2. **Ingestion Pipeline (`pipelines/ingestion_pipeline.py`)**: ✅ Complete.
   - Loads `transaction_raw.csv` and `identity_raw.csv` from `dataset/raw/` into PostgreSQL tables `transaction_raw` and `identity_raw`.
   - Verified working with test runner.

3. **Validation Pipeline (`pipelines/validation_pipeline.py`)**: ✅ Complete.
   - Validates data in PostgreSQL: empty table checks, NULL primary keys, NULL `isFraud` target, duplicate `TransactionID` checks.
   - Generates `dataset/validation_reports/validation_report.json`.
   - Both tables passed: `transaction_raw` (590,540 rows) and `identity_raw` (144,233 rows).
   - Verified working with `tests/unit/validation_pipeline_test.py`.

4. **Cleaning Pipeline (`pipelines/cleaning_pipeline.py`)**: ✅ Complete (partial — column dropping done, missing value handling still TODO).
   - Loads only the required columns (`SELECTED_FEATURES_TO_KEEP` from constants) at query time — avoids loading all 394 columns.
   - Reads data in chunks of 50,000 rows and downcasts `float64` → `float32` to prevent `ArrayMemoryError` on systems with limited RAM.
   - Merges `transaction_raw` + `identity_raw` on `TransactionID` (left join) and verifies row count is unchanged post-merge.
   - Drops the 149 columns not in the keep-list.
   - Frees intermediate DataFrames immediately post-merge using `del` + `gc.collect()`.
   - Verified working: 590,540 rows × 285 columns after drop.
   - **Remaining TODO**: `_filling_missing_values()` method (currently commented out) — fill NaNs per column strategy, extract `addr1_missing`/`addr2_missing` flags, save cleaned output to `dataset/processed/cleaned.parquet`.

5. **Bug Fixes & Infrastructure**:
   - **Circular import fix** (`shared/logging/logging_config.py`): Changed `from shared import constants` → `from shared.constants import constants` to avoid the logger module importing from an uninitialized `shared` package.
   - **Log file override fix** (`shared/logging/logging_config.py`): Added `force=True` to `logging.basicConfig()` so each pipeline can reconfigure the root logger to its own log file (e.g., `cleaning.log`) even when another module has already initialized logging.
   - **Ruff linting fixes**:
     - `database/connection.py` E402: Moved `from sqlalchemy import create_engine, text` above the `configure_logging()` call.
     - `shared/__init__.py` F403/F405: Replaced `from shared.logging.logging_config import *` with explicit `from shared.logging.logging_config import configure_logging`.
     - `pyproject.toml` deprecation warning: `select` should be moved to `[tool.ruff.lint]` section — **still TODO**.
     - `tests/unit/logging_testing.py` E501: Line too long — **still TODO** (user denied write permission last time).

### Running Pipeline Scripts / Tests

Always activate the conda environment and set `PYTHONPATH` before running any script:

```powershell
# Step 1: Activate the conda environment
conda activate financial_risk_intelligence

# Step 2: From the project root, set PYTHONPATH and run
$env:PYTHONPATH = "."
python tests/unit/validation_pipeline_test.py
python tests/unit/cleaning_pipeline_test.py
```

Or using conda run (no need to activate manually):
```powershell
$env:PYTHONPATH = "."; conda run -n financial_risk_intelligence python tests/unit/cleaning_pipeline_test.py
```

### Known Issues / Gotchas

- **Do NOT use `SELECT *`** when loading from PostgreSQL in this project — the transaction table has 394 columns and will trigger `ArrayMemoryError` on low-RAM machines. Always filter columns at query time using `SELECTED_FEATURES_TO_KEEP`.
- **`TransactionDT` is NOT a real timestamp** — it is a timedelta in seconds from an unknown reference point. Never parse it as a datetime.
- **`addr1`/`addr2`** have high NaN rates that are disproportionately fraud (~37%). Do NOT drop them — extract `addr1_missing` / `addr2_missing` binary flags instead in `feature_engineering_pipeline.py`.

### Next Steps & Tasks

- [ ] **Complete `cleaning_pipeline.py`**: Implement `_filling_missing_values()` — per-column fill strategies (median for numeric, mode for categorical), extract `addr1_missing` / `addr2_missing` flags, and save final output to `dataset/processed/cleaned.parquet`.
- [ ] **Fix remaining ruff lint warnings**:
  - Move `select = [...]` to `[tool.ruff.lint]` in `pyproject.toml`.
  - Shorten long line in `tests/unit/logging_testing.py`.
- [ ] **Implement `feature_engineering_pipeline.py`**: Build behavioral, temporal, email-domain, and device features on top of `cleaned.parquet`.
- [ ] **Implement `dataset_builder_pipeline.py`**: Group-aware train/val/test split using `StratifiedGroupKFold`, encode categoricals, scale numerics, write `train.parquet`, `validation.parquet`, `test.parquet`.
