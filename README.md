# 🛡️ Adaptive Financial Risk Intelligence Engine (--In Development--)

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![MLflow](https://img.shields.io/badge/MLflow-Tracking_%26_Registry-0194E2.svg)](https://mlflow.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-<100ms_SLA-009688.svg)](https://fastapi.tiangolo.com/)
[![Redis](https://img.shields.io/badge/Redis-Online_Feature_Store-DC382D.svg)](https://redis.io/)
[![Terraform](https://img.shields.io/badge/Terraform-AWS_IaC-844FBA.svg)](https://www.terraform.io/)

## Project Overview

A production-grade Machine Learning Operations (MLOps) system for real-time financial fraud detection. Built with a focus on enterprise-readiness, this project emphasizes **strict latency SLAs, automated model lifecycles, and decoupled explainability**, pushing beyond standalone Jupyter notebooks into a true end-to-end engineering architecture.

The core challenge involves analyzing highly imbalanced transactional data (~3.5% fraud rate) and maintaining a high Precision-Recall AUC (>0.49) while ensuring legitimate customer transactions are not bottlenecked or falsely declined.

---

## 🚀 Key MLOps Architectural Highlights

*   🏆 **Champion/Challenger Model Registry (MLflow)**
    Architected a 14-stage, class-based MLOps pipeline automating ETL, Optuna hyperparameter tuning, and model registration. The system enforces a strict Champion/Challenger promotion strategy, automatically comparing new models against production baselines before safely promoting high-recall algorithms.
*   ⚡ **Ultra-Low Latency Serving (<100ms SLA)**
    Engineered a high-performance FastAPI inference layer backed by a Redis Online Feature Store. By bypassing heavy relational database lookups during live predictions, the system guarantees a sub-100ms prediction SLA.
*   🧠 **Decoupled Explainability (SHAP)**
    Because SHAP (SHapley Additive exPlanations) computation is too slow for real-time APIs, prediction and explainability are physically decoupled. Heavy computations run asynchronously, translating complex arrays into human-readable fraud rationales for analysts (e.g., *"Transaction amount is 4.2x customer average"*).
*   🔄 **Automated Retraining & Drift Monitoring**
    Integrated Evidently AI for continuous production monitoring. The system tracks feature distribution and concept drift, automatically triggering Airflow retraining pipelines to maintain robust precision/recall metrics over time.
*   🏗️ **Scalable Infrastructure (AWS + Terraform)**
    Provisioned AWS infrastructure (ECS, RDS, ElastiCache) entirely via Terraform. Fully containerized microservices via Docker and GitHub Actions establish a zero-downtime, automated CI/CD lifecycle.

---

## 🏗️ The 14-Stage Pipeline Architecture

Every stage in this system extends a core `BasePipeline` class, ensuring consistent logging, error handling, and orchestration compatibility with Apache Airflow.

1.  **Ingestion:** Raw transaction tracking into PostgreSQL.
2.  **Validation:** Schema, null, and duplicate assertions.
3.  **Cleaning:** Type conversions and structural normalization.
4.  **Feature Engineering:** Temporal, device, and behavioral feature generation.
5.  **Dataset Builder:** Group-aware (StratifiedGroupKFold) splitting.
6.  **Training:** XGBoost/LightGBM training with integrated MLflow tracking.
7.  **Evaluation:** Cost-sensitive business metrics (PR-AUC, Recall, Confusion Matrix).
8.  **Calibration:** Platt scaling / Isotonic regression for raw risk scoring (0-100).
9.  **Registration:** The Champion vs. Challenger MLflow registry showdown.
10. **Serving:** The `<100ms` FastAPI inference engine.
11. **Explainability:** Asynchronous SHAP baseline evaluation.
12. **Monitoring:** Evidently AI drift and performance tracking.
13. **Retraining:** Event-driven retraining loops based on drift metrics.
14. **Deployment:** CI/CD container lifecycle to AWS ECS.

---

## 🛠️ Technology Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Modeling** | XGBoost, LightGBM, Scikit-learn | Imbalanced classification, gradient boosted trees |
| **Explainability** | SHAP | Decoupled, human-readable fraud rationales |
| **Experiment Tracking** | MLflow | Hyperparameter tracking, Model Registry (Champion/Challenger) |
| **Orchestration** | Apache Airflow | Pipeline scheduling and DAG execution |
| **Serving Layer** | FastAPI, Uvicorn | Real-time REST endpoints (`/predict`, `/explain`) |
| **Data & Cache** | PostgreSQL, Redis | Relational storage & O(1) Online Feature Store lookups |
| **Monitoring** | Evidently AI | Data drift and prediction drift alerting |
| **Infrastructure** | Terraform, Docker, AWS | IaC (ECS, ElastiCache, RDS) and containerization |

---

## 🚀 Getting Started (Local Development)

**1. Clone the repository & Environment Setup**
```bash
git clone https://github.com/abhi24112/Financial_Risk_Intelligence_Engine_MLOps.git
cd Financial_Risk_Intelligence_Engine_MLOps

# Activate your conda environment
conda activate financial_risk_intelligence
```

**2. Spin up the Infrastructure**
This will start PostgreSQL (Database), Redis (Feature Store), and MLflow.
```bash
docker-compose up -d
```

**3. Run the Core Pipelines**
Our core ML logic is executed via dedicated CLI scripts built on top of our pipeline classes:

```bash
# Set PYTHONPATH for local execution
$env:PYTHONPATH = "."  # Windows PowerShell
# export PYTHONPATH="."  # Mac/Linux

# Run Hyperparameter Tuning (Optuna)
python scripts/tune.py --model lightgbm

# Train the optimal model and log to MLflow
python scripts/train.py --config model.yaml

# Promote the best model to Production via the Registry
python scripts/register.py --config model.yaml
```

**4. View MLflow Dashboard**
View your tuning trials and Model Registry UI:
```bash
mlflow ui --backend-store-uri sqlite:///mlflow.db
```
