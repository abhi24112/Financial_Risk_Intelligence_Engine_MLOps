import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class PipelineResult:
    """
    Standardized output for all pipelines, easily readable by Airflow/MLflow.
    """

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

    def __init__(self, config: dict[str, Any] | None = None):
        # We can pass configurations (like paths, model params) through this dict
        self.config = config or {}
        # Automatically sets up the logger
        self.logger = logging.getLogger(self.__class__.__name__)
        self.name = self.__class__.__name__

    @abstractmethod
    def _execute(self) -> dict[str, Any]:
        """
        Business logic for this specific pipeline stage.
        Must return a dict containing 'artifacts' and/or 'metadata' to attach to PipelineResult.
        """
        raise NotImplementedError

    def run(self) -> PipelineResult:
        """
        The Template Method. This is the only method that should be called externally.
        It handles timing, error catching, standardizing the output, and generating a report.
        """
        started_at = datetime.now(UTC)
        self.logger.info(f"[{self.name}] starting")

        try:
            # 1. Call the child class's specific business logic
            output = self._execute()
            if output is None:
                output = {}

            # 2. Package the result perfectly
            result = PipelineResult(
                pipeline_name=self.name,
                status="success",
                started_at=started_at,
                finished_at=datetime.now(UTC),
                artifacts=output.get("artifacts", {}),
                metadata=output.get("metadata", {}),
            )
            self.logger.info(f"[{self.name}] completed successfully")

            # Automatically save the report for ALL pipelines
            self._save_report(result)
            return result

        except Exception as exc:
            # 3. If ANYTHING fails, the base class catches it and logs it safely
            self.logger.exception(f"[{self.name}] failed: {exc}")
            result = PipelineResult(
                pipeline_name=self.name,
                status="failed",
                started_at=started_at,
                finished_at=datetime.now(UTC),
                error=str(exc),
            )
            self._save_report(result)
            return result

    def _save_report(self, result: PipelineResult) -> None:
        """Automatically saves the pipeline result as a JSON report."""
        report_dir = "dataset/reports"
        os.makedirs(report_dir, exist_ok=True)
        report_path = os.path.join(report_dir, f"{self.name.lower()}_report.json")

        # Convert dataclass to dict, handle datetime serialization
        def default_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Type {type(obj)} not serializable")

        with open(report_path, "w") as f:
            json.dump(asdict(result), f, indent=4, default=default_serializer)

        self.logger.info(f"[{self.name}] Report saved to {report_path}")
