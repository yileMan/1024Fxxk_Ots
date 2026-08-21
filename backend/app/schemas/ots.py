from datetime import datetime

from pydantic import BaseModel, Field


class OtsCreateRequest(BaseModel):
    ots_name: str = Field(min_length=1, max_length=200)
    ots_version: str = Field(min_length=1, max_length=200)
    official_website: str = Field(min_length=1, max_length=1000, pattern=r"^https?://")
    is_eol: bool


class OtsUpdateRequest(OtsCreateRequest):
    row_version: int = Field(ge=1)


class OtsResponse(BaseModel):
    id: int
    ots_name: str
    ots_version: str
    official_website: str
    is_eol: bool
    row_version: int
    created_at: datetime
    updated_at: datetime


class OtsPageResponse(BaseModel):
    items: list[OtsResponse]
    total: int
    page: int
    page_size: int


class ProductOtsCreateRequest(BaseModel):
    ots_component_id: int = Field(ge=1)


class ProductOtsResponse(BaseModel):
    id: int
    product_version_id: int
    ots_component_id: int
    created_by: int
    created_at: datetime
    updated_at: datetime
    ots_name: str
    ots_version: str
    official_website: str
    is_eol: bool


class OtsProductVersionResponse(BaseModel):
    product_ots_id: int
    product_id: int
    product_code: str
    product_name: str
    product_version_id: int
    version_no: str
    status: str


class CsvImportErrorResponse(BaseModel):
    row: int
    field: str
    reason: str


class CsvImportResultResponse(BaseModel):
    created_ots: int
    created_relations: int
    existing_relations: int
