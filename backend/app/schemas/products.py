from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ProductCreateRequest(BaseModel):
    product_code: str = Field(min_length=1, max_length=64)
    product_name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class ProductUpdateRequest(ProductCreateRequest):
    row_version: int = Field(ge=1)


class VersionCreateRequest(BaseModel):
    version_no: str = Field(min_length=1, max_length=100)
    description: str | None = None
    owner_id: int = Field(ge=1)
    reviewer_id: int = Field(ge=1)


class VersionUpdateRequest(VersionCreateRequest):
    row_version: int = Field(ge=1)


class DisableRequest(BaseModel):
    row_version: int = Field(ge=1)


class ProductResponse(BaseModel):
    id: int
    product_code: str
    product_name: str
    description: str | None
    status: Literal["active", "disabled"]
    row_version: int
    created_at: datetime
    updated_at: datetime


class ProductVersionResponse(BaseModel):
    id: int
    product_id: int
    version_no: str
    description: str | None
    primary_cvss_version: Literal["3.1"]
    owner_id: int
    reviewer_id: int
    status: Literal["active", "disabled"]
    row_version: int
    created_at: datetime
    updated_at: datetime


class ProductPageResponse(BaseModel):
    items: list[ProductResponse]
    total: int
    page: int
    page_size: int
