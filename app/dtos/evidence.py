from datetime import datetime

from pydantic import BaseModel


class EvidencePhotoUploadResponse(BaseModel):
    evidence_url: str
    uploaded_at: datetime
