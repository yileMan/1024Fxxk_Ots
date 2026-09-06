from datetime import datetime

from pydantic import BaseModel


class AssessmentExportPreviewResponse(BaseModel):
    product_version_id: int
    product_name: str
    version_no: str
    ots_id: int
    ots_name: str
    ots_version: str
    row_count: int
    previewed_at: datetime
