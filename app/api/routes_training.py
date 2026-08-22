"""
app/api/routes_training.py
==========================
LoRA Fine-Tuning & Model Version Lineage API Endpoints (Phase 5).
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel

from app.core.training_pipeline import LoRATrainingPipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/training", tags=["LoRA Fine-Tuning & Model Versioning"])


class TriggerTrainingRequest(BaseModel):
    epochs: int = 5
    learning_rate: float = 2e-4
    batch_size: int = 16
    triggered_by: str = "Lead Forensic Examiner"


@router.post("/trigger")
def trigger_lora_training(body: TriggerTrainingRequest = Body(default=TriggerTrainingRequest())):
    """Trigger an asynchronous LoRA fine-tuning session on verified dataset samples."""
    return LoRATrainingPipeline.trigger_training(
        epochs=body.epochs,
        learning_rate=body.learning_rate,
        batch_size=body.batch_size,
        triggered_by=body.triggered_by
    )


@router.get("/status")
def get_training_status():
    """Retrieve live status, loss, validation accuracy, and logs of the active training session."""
    return LoRATrainingPipeline.get_training_status()


@router.get("/versions")
def list_model_versions():
    """List all model checkpoint versions, training accuracy, and active states."""
    versions = LoRATrainingPipeline.list_model_versions()
    return {
        "total_versions": len(versions),
        "versions": versions
    }


@router.post("/rollback/{version_id}")
def rollback_model_version(version_id: str):
    """Roll back / activate a specific model version checkpoint."""
    try:
        return LoRATrainingPipeline.rollback_model_version(version_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
