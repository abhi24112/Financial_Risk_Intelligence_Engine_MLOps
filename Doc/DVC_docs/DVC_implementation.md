# DVC Implementation — Adaptive Financial Risk Intelligence Engine

## 1. Overview & Architecture

**DVC (Data Version Control)** is integrated into the Adaptive Financial Risk Intelligence Engine to ensure data lineage, pipeline reproducibility, and version control for large dataset artifacts and trained model weights without bloating the Git repository.

### Separation of Concerns: DVC vs. MLflow
| Responsibility | Tool | Implementation |
| :--- | :--- | :--- |
| **Data Versioning & Lineage** | **DVC** | Tracks parquet datasets (`cleaned.parquet`, `features.parquet`, `train/val/test.parquet`) and production `.skops` weights in remote storage. |
| **Experiment Tracking & Showdown** | **MLflow** | Tracks hyperparameters, PR-AUC / ROC-AUC / Recall metrics, runs history (`sqlite:///mlflow.db`), and Champion/Challenger Model Registry. |
| **Code & Config Versioning** | **Git** | Tracks pipeline code, `configs/*.yaml`, `dvc.yaml`, `params.yaml`, and `.dvc` pointer files. |

---

## 2. Pipeline Dependency Graph (`dvc.yaml`)

The data pipeline stages are codified in [`dvc.yaml`](../../dvc.yaml) with explicit dependencies (`deps`) and outputs (`outs`):

```
      +----------+       
      | cleaning |       
      +----------+       
            *            
            *            
            *            
+---------------------+  
| feature_engineering |  
+---------------------+  
            *            
            *            
            *            
  +-----------------+    
  | dataset_builder |    
  +-----------------+    
```

### Codified Stages
1. **`cleaning`**:
   - **Command**: `python pipelines/cleaning_pipeline.py`
   - **Dependencies**: `pipelines/cleaning_pipeline.py`, `database/loader.py`, `database/connection.py`
   - **Output**: `dataset/interim/cleaned.parquet` (57.1 MB)
2. **`feature_engineering`**:
   - **Command**: `python pipelines/feature_engineering_pipeline.py`
   - **Dependencies**: `pipelines/feature_engineering_pipeline.py`, `dataset/interim/cleaned.parquet`
   - **Output**: `dataset/processed/features.parquet` (80.4 MB)
3. **`dataset_builder`**:
   - **Command**: `python pipelines/dataset_builder_pipeline.py`
   - **Dependencies**: `pipelines/dataset_builder_pipeline.py`, `dataset/processed/features.parquet`
   - **Parameters**: `dataset.split_folds`, `dataset.random_state`
   - **Outputs**:
     - `dataset/processed/train.parquet` (58.1 MB)
     - `dataset/processed/val.parquet` (12.4 MB)
     - `dataset/processed/test.parquet` (12.2 MB)

---

## 3. Configuration & Parameters

### 3.1 [`params.yaml`](../../params.yaml)
Defines reproducibility knobs tracked by DVC:
```yaml
dataset:
  target: "isFraud"
  group_col: "uid_card"
  split_folds: 7
  random_state: 42

train:
  model_type: "xgboost"
  random_state: 42
  max_depth: 5
  learning_rate: 0.05
  n_estimators: 150
  subsample: 0.8
  colsample_bytree: 0.8
```

### 3.2 [`.dvcignore`](../../.dvcignore)
Ensures caches, test directories, local runtime logs, and SQLite DB files are excluded from DVC tracking:
```gitignore
.git/
.vscode/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
logs/
mlflow.db
mlruns/
```

---

## 4. Tracked Artifacts & Remote Storage

### 4.1 Tracked Assets (Total: 7 Files)
- **Data Parquet Files**:
  - `dataset/interim/cleaned.parquet`
  - `dataset/processed/features.parquet`
  - `dataset/processed/train.parquet`
  - `dataset/processed/val.parquet`
  - `dataset/processed/test.parquet`
- **Model Artifacts**:
  - `models/production_model.skops` (Champion Model) ➔ tracked via `models/production_model.skops.dvc`
  - `models/challenger_model.skops` (Challenger Model) ➔ tracked via `models/challenger_model.skops.dvc`

### 4.2 Local Remote Storage Setup
- **Storage Location**: `../dvc_remote_storage` (simulates S3 / GCS cloud bucket storage locally).
- **Default Remote Name**: `local_storage`
- **Push Verification**: All 7 files hashed and synced via `dvc push`.

---

## 5. Operational Commands & Runbook

Activate the environment before running DVC commands:

```powershell
conda activate financial_risk_intelligence
$env:PYTHONPATH = "."
```

### 5.1 View Pipeline Graph
```powershell
dvc dag
```

### 5.2 Check Status
```powershell
dvc status
```
*Expected Output:*
```text
Data and pipelines are up to date.
```

### 5.3 Push / Pull Remote Data
```powershell
# Push all data and model artifacts to remote storage
dvc push

# Pull data and model artifacts on a new clone/environment
dvc pull
```

### 5.4 Reproduce Data Pipeline
```powershell
# Reproduce any modified stages
dvc repro

# Force reproduction of all stages
dvc repro -f
```

