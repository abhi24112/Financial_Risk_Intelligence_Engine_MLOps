"""
Airflow DAG: financial_risk_drift_monitoring
Automated continuous data and prediction drift monitoring using Evidently AI.
Conditionally triggers retraining when feature drift exceeds the configured threshold.
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Any

from airflow.exceptions import AirflowException
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator, PythonOperator

from airflow import DAG

# Ensure project root is in PYTHONPATH
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pipelines.monitoring_pipeline import MonitoringPipeline
from pipelines.retraining_pipeline import RetrainingPipeline
from shared.config_loader import load_config
from shared.logger import get_logger

logger = get_logger("AirflowMonitoringDAG")


def _get_monitoring_config() -> dict[str, Any]:
    """Loads configs/airflow.yaml monitoring config."""
    try:
        cfg = load_config("airflow.yaml")
        return cfg.get("monitoring_dag", {})
    except Exception as exc:
        logger.warning(f"Could not load airflow.yaml ({exc}). Using defaults.")
        return {}


dag_config = _get_monitoring_config()
default_args_cfg = dag_config.get("default_args", {})

default_args = {
    "owner": default_args_cfg.get("owner", "mlops_team"),
    "depends_on_past": default_args_cfg.get("depends_on_past", False),
    "start_date": datetime(2026, 1, 1),
    "retries": default_args_cfg.get("retries", 1),
    "retry_delay": timedelta(seconds=default_args_cfg.get("retry_delay_seconds", 120)),
    "email_on_failure": default_args_cfg.get("email_on_failure", False),
}


def _run_drift_monitoring(**context: Any) -> dict[str, Any]:
    """Runs Evidently AI drift monitoring and pushes metadata to XCom."""
    try:
        config = load_config("monitoring.yaml")
    except Exception:
        config = {}

    pipeline = MonitoringPipeline(config)
    result = pipeline.run()

    if result.status != "success":
        raise AirflowException(f"MonitoringPipeline failed: {result.error}")

    ti = context.get("ti")
    if ti and result.metadata:
        for k, v in result.metadata.items():
            ti.xcom_push(key=k, value=v)

    return result.metadata


def _evaluate_drift_trigger(**context: Any) -> str:
    """Branches to retraining if drift threshold is exceeded, else skips."""
    ti = context.get("ti")
    retraining_triggered = False
    if ti:
        retraining_triggered = ti.xcom_pull(task_ids="check_data_drift", key="retraining_triggered")

    if retraining_triggered:
        logger.warning("Dataset drift detected! Branching to automated retraining.")
        return "trigger_automated_retraining"
    else:
        logger.info("No significant drift detected. Branching to safe completion.")
        return "drift_safe_completion"


def _run_retraining(**context: Any) -> dict[str, Any]:
    """Runs end-to-end RetrainingPipeline when drift is detected."""
    pipeline = RetrainingPipeline()
    result = pipeline.run()

    if result.status != "success":
        raise AirflowException(f"RetrainingPipeline failed: {result.error}")

    return result.metadata


with DAG(
    dag_id=dag_config.get("dag_id", "financial_risk_drift_monitoring"),
    description=dag_config.get("description", "Continuous drift monitoring & conditional retraining"),
    default_args=default_args,
    schedule_interval=dag_config.get("schedule_interval", "0 2 * * *"),
    catchup=dag_config.get("catchup", False),
    max_active_runs=dag_config.get("max_active_runs", 1),
    tags=["mlops", "financial-risk", "monitoring", "evidently", "drift"],
) as dag:

    # 1. Run Evidently AI Data & Feature Drift Checks
    task_check_drift = PythonOperator(
        task_id="check_data_drift",
        python_callable=_run_drift_monitoring,
    )

    # 2. Evaluate Drift Threshold
    task_evaluate_drift = BranchPythonOperator(
        task_id="evaluate_drift_trigger",
        python_callable=_evaluate_drift_trigger,
    )

    # 3a. Branch: Drift detected -> Execute Retraining Flow
    task_retrain = PythonOperator(
        task_id="trigger_automated_retraining",
        python_callable=_run_retraining,
    )

    # 3b. Branch: No drift -> Safe completion
    task_safe = EmptyOperator(
        task_id="drift_safe_completion",
    )

    # Dependency routing
    task_check_drift >> task_evaluate_drift >> [task_retrain, task_safe]
