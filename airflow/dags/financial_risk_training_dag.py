"""
Airflow DAG: financial_risk_training_pipeline
Orchestrates the end-to-end ML lifecycle:
Ingest -> Validate -> Clean -> Feature Engineer -> Dataset Builder -> Train -> Evaluate -> Register
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Any

from airflow.exceptions import AirflowException
from airflow.operators.python import PythonOperator

from airflow import DAG

# Ensure project root is in PYTHONPATH
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from pipelines.base_pipeline import BasePipeline
from pipelines.cleaning_pipeline import CleaningPipeline
from pipelines.dataset_builder_pipeline import DatasetBuilderPipeline
from pipelines.evaluation_pipeline import EvaluationPipeline
from pipelines.feature_engineering_pipeline import FeatureEngineeringPipeline
from pipelines.ingestion_pipeline import IngestionPipeline
from pipelines.registration_pipeline import RegistrationPipeline
from pipelines.training_pipeline import TrainingPipeline
from pipelines.validation_pipeline import ValidationPipeline
from shared.config_loader import load_config
from shared.logger import get_logger

logger = get_logger("AirflowTrainingDAG")


def _get_dag_config() -> dict[str, Any]:
    """Loads configs/airflow.yaml with sensible defaults."""
    try:
        cfg = load_config("airflow.yaml")
        return cfg.get("training_dag", {})
    except Exception as exc:
        logger.warning(f"Could not load airflow.yaml ({exc}). Using defaults.")
        return {}


dag_config = _get_dag_config()
default_args_cfg = dag_config.get("default_args", {})

default_args = {
    "owner": default_args_cfg.get("owner", "mlops_team"),
    "depends_on_past": default_args_cfg.get("depends_on_past", False),
    "start_date": datetime(2026, 1, 1),
    "retries": default_args_cfg.get("retries", 2),
    "retry_delay": timedelta(seconds=default_args_cfg.get("retry_delay_seconds", 180)),
    "email_on_failure": default_args_cfg.get("email_on_failure", False),
}


def _execute_stage(pipeline_cls: type[BasePipeline], config_file: str | None = None, **context: Any) -> dict[str, Any]:
    """
    Standardized executor for class-based pipelines within Airflow.
    Runs the pipeline, pushes metadata to XCom, and raises AirflowException on failure.
    """
    stage_name = pipeline_cls.__name__
    logger.info(f"Airflow Task [{stage_name}] execution started.")

    config = {}
    if config_file:
        try:
            config = load_config(config_file)
        except Exception as exc:
            logger.warning(f"Failed to load config {config_file}: {exc}. Using empty config.")

    # Instantiate class-based pipeline
    pipeline = pipeline_cls(config)
    result = pipeline.run()

    if result.status != "success":
        error_msg = f"Pipeline [{stage_name}] failed. Error: {result.error}"
        logger.error(error_msg)
        raise AirflowException(error_msg)

    logger.info(f"Pipeline [{stage_name}] completed successfully.")

    # Push execution metadata to XCom for observability
    ti = context.get("ti")
    if ti and result.metadata:
        for k, v in result.metadata.items():
            ti.xcom_push(key=k, value=v)

    return result.metadata


with DAG(
    dag_id=dag_config.get("dag_id", "financial_risk_training_pipeline"),
    description=dag_config.get("description", "End-to-end ML training and promotion pipeline"),
    default_args=default_args,
    schedule_interval=dag_config.get("schedule_interval", "0 0 * * 0"),
    catchup=dag_config.get("catchup", False),
    max_active_runs=dag_config.get("max_active_runs", 1),
    tags=["mlops", "financial-risk", "training", "champion-challenger"],
) as dag:

    # 1. Ingestion Stage (Raw CSV -> PostgreSQL)
    task_ingest = PythonOperator(
        task_id="ingest_raw_data",
        python_callable=_execute_stage,
        op_kwargs={"pipeline_cls": IngestionPipeline},
    )

    # 2. Validation Stage (Schema, Primary Keys & Quality Guardrail)
    task_validate = PythonOperator(
        task_id="validate_raw_data",
        python_callable=_execute_stage,
        op_kwargs={"pipeline_cls": ValidationPipeline},
    )

    # 3. Cleaning Stage (Downcast, Null Imputation, Parquet Export)
    task_clean = PythonOperator(
        task_id="clean_transactions",
        python_callable=_execute_stage,
        op_kwargs={"pipeline_cls": CleaningPipeline},
    )

    # 4. Feature Engineering Stage (Behavioral Aggregates & Velocity)
    task_feature_engineer = PythonOperator(
        task_id="engineer_features",
        python_callable=_execute_stage,
        op_kwargs={"pipeline_cls": FeatureEngineeringPipeline},
    )

    # 5. Dataset Builder Stage (StratifiedGroupKFold Group-Aware Split)
    task_dataset_builder = PythonOperator(
        task_id="build_datasets",
        python_callable=_execute_stage,
        op_kwargs={"pipeline_cls": DatasetBuilderPipeline},
    )

    # 6. Training Stage (Model Training & MLflow Run Logging)
    task_train = PythonOperator(
        task_id="train_model",
        python_callable=_execute_stage,
        op_kwargs={"pipeline_cls": TrainingPipeline, "config_file": "model.yaml"},
    )

    # 7. Evaluation Stage (PR-AUC, ROC-AUC, Recall Metrics Calculation)
    task_evaluate = PythonOperator(
        task_id="evaluate_model",
        python_callable=_execute_stage,
        op_kwargs={"pipeline_cls": EvaluationPipeline, "config_file": "model.yaml"},
    )

    # 8. Champion Registration Stage (Champion vs Challenger Showdown)
    task_register = PythonOperator(
        task_id="register_champion",
        python_callable=_execute_stage,
        op_kwargs={"pipeline_cls": RegistrationPipeline, "config_file": "model.yaml"},
    )

    # Define strict pipeline dependency order
    (task_ingest >> task_validate >> task_clean >> task_feature_engineer >> task_dataset_builder >> task_train >> task_evaluate >> task_register)
