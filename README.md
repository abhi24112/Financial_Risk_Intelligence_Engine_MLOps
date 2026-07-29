# 🕵️‍♂️ Transaction Fraud Detection Pipeline

## Project Overview

This repository contains an end-to-end Machine Learning pipeline for detecting fraudulent financial transactions. Built with a focus on production-readiness, the project emphasizes aggressive data leakage prevention, strict mathematical feature selection, and optimized data preprocessing for high-performance inference.

The dataset includes transaction metadata, anonymized categorical identities, time-delta behavioral features, and heavily engineered numerical aggregates.

---

## 🏗️ Pipeline Architecture

### Phase 1: Exploratory Data Analysis & Feature Selection (✅ Completed)

The EDA phase prioritized isolating pure predictive signals from structural noise and data leakage using advanced statistical filtering.

* **Dimensionality Reduction via Network Graphing:** Analyzed 339 highly collinear engineered features. By building a correlation network graph with a 0.95 threshold, **136 perfectly redundant features** were clustered and dropped, massively reducing downstream compute costs.
* **Information Value (IV) & WOE Filtering:** Replaced basic linear Pearson correlation with Weight of Evidence (WOE) and Information Value (IV) to capture non-linear fraud relationships. Features with an IV < 0.02 were dropped as noise.
* **Automated Data Leakage Defense:** Built a programmatic auditor to evaluate "suspiciously strong" features (IV >= 0.5). Structural leakers (features demonstrating >95% or exactly 0.0% fraud rates over high volumes) were permanently removed to ensure the model generalizes in production rather than memorizing post-transaction flags.

### Phase 2: Data Preprocessing (🚧 Next)

The feature engineering pipeline is designed specifically for tree-based algorithms (LightGBM/XGBoost) to avoid dimensionality explosion.

* **Target & Frequency Encoding:** High-cardinality categorical features (e.g., identity configurations, device info) will be processed using k-fold smoothed Target Encoding and Frequency Encoding rather than One-Hot Encoding (OHE).
* **Missingness as a Signal:** NaNs in this dataset are highly predictive (e.g., missing address fields correlate with a ~37% fraud rate). Numerical NaNs will be imputed with out-of-range values (e.g., `-999`) to allow algorithms to natively split on the absence of data.

### Phase 3: Model Training & Evaluation (⏳ Upcoming)

* **Algorithm:** Gradient Boosted Decision Trees (XGBoost / LightGBM) optimized for imbalanced classification.
* **Metrics:** The model will be evaluated primarily on **ROC-AUC** and **Precision-Recall (PR) AUC** to accurately measure performance on highly skewed classes.

---

## 📂 Repository Structure

```text
Adaptive-Financial-Risk-Intelligence-Engine/
├── .github/
├── airflow/
├── api/
├── apps/
├── configs/
├── data/
├── database/
├── deployment/
├── docker/
├── docs/
├── dvc/
├── explainability/
├── feature_store
├── infrastructure/
├── ml/
├── monitoring/
├── pipelines/
├── scripts/
├── shared/
├── tests/
├── notebooks/
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── README.md
└── Makefile

```

---

## 🛠️ Tech Stack

* **Language:** Python 3.10+
* **Data Processing:** Pandas, NumPy
* **Feature Selection & Network Analysis:** NetworkX, SciPy
* **Visualization:** Matplotlib, Seaborn

---

## 🚀 Getting Started

**1. Clone the repository**

```bash
git clone https://github.com/abhi24112/Financial_Risk_Intelligence_Engine_MLOps.git
cd fraud-detection-pipeline

```

**2. Install dependencies**

```bash
pip install -r requirements.txt

```

**3. Run the EDA & Feature Selection**
Execute the main exploratory notebook in the `notebooks/` directory to generate the optimized feature lists and prune the raw data.