from datetime import datetime

from pydantic import BaseModel


class TimestampedModel(BaseModel):
    created_at: datetime | None = None
    updated_at: datetime | None = None
