from typing import Literal

from pydantic import BaseModel, Field


AlertSourceType = Literal["prazo", "tarefa", "intimacao", "movimentacao"]
AlertAcknowledgementState = Literal["visualizado", "tratado"]


class ActivityAlertStateUpdate(BaseModel):
    estado: AlertAcknowledgementState


class SmartAlertQuery(BaseModel):
    limit_per_type: int = Field(default=5, ge=1, le=10)
