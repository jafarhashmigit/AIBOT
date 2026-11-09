"""Model registry. Phase 6 forbids PRODUCTION status."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from phase6.constants import ALLOW_PRODUCTION, REGISTRY_SCHEMA_VERSION, SEED

STATUSES = ("EXPERIMENTAL", "VALIDATED", "CANDIDATE", "REJECTED", "PRODUCTION")


class RegistryError(ValueError):
    pass


@dataclass
class ModelRecord:
    model_id: str
    model_type: str
    feature_version: str
    training_start: str
    training_end: str
    training_rows: int
    training_timestamp: str
    random_seed: int
    hyperparameters: dict
    code_version: str
    evaluation_protocol: str
    status: str
    registry_schema_version: str = REGISTRY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise RegistryError(f"unknown status {self.status}")
        if self.status == "PRODUCTION" and not ALLOW_PRODUCTION:
            raise RegistryError("No model may be marked PRODUCTION in Phase 6")


@dataclass
class ModelRegistry:
    records: dict[str, ModelRecord] = field(default_factory=dict)

    def register(self, record: ModelRecord) -> ModelRecord:
        if record.status == "PRODUCTION" and not ALLOW_PRODUCTION:
            raise RegistryError("No model may be marked PRODUCTION in Phase 6")
        if record.model_id in self.records:
            raise RegistryError(f"model_id already registered: {record.model_id}")
        self.records[record.model_id] = record
        return record

    def get(self, model_id: str) -> ModelRecord:
        return self.records[model_id]

    def set_status(self, model_id: str, status: str) -> ModelRecord:
        if status == "PRODUCTION" and not ALLOW_PRODUCTION:
            raise RegistryError("No model may be marked PRODUCTION in Phase 6")
        if status not in STATUSES:
            raise RegistryError(f"unknown status {status}")
        current = self.records[model_id]
        updated = ModelRecord(**{**asdict(current), "status": status})
        self.records[model_id] = updated
        return updated

    def to_mapping(self) -> dict[str, Any]:
        return {k: asdict(v) for k, v in self.records.items()}


def experimental_stub() -> ModelRecord:
    return ModelRecord(
        model_id="no_model",
        model_type="null",
        feature_version="m5_utc_corrected_allowlist_v1",
        training_start="",
        training_end="",
        training_rows=0,
        training_timestamp="",
        random_seed=SEED,
        hyperparameters={},
        code_version="phase6_oos_signal_protocol_v1",
        evaluation_protocol="architecture_only",
        status="EXPERIMENTAL",
    )
