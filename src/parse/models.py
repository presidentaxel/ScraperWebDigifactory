"""Data models for scraped records."""
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


class SaleRecord(BaseModel):
    """Complete sale record extracted from DigiFactory pages."""

    nr: int = Field(..., description="Sale number (primary key)")
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="ok", description="ok, not_found, auth_error, failed")
    data: dict[str, Any] = Field(default_factory=dict, description="All extracted data")
    raw: Optional[str] = Field(default=None, description="Compressed HTML (optional)")
    hash: Optional[str] = Field(default=None, description="Content hash for change detection")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }

