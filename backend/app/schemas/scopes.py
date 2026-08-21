from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ScopeGrantRequest(BaseModel):
    scope_type: Literal["product", "version"]
    product_id: int = Field(ge=1)
    product_version_id: int | None = Field(default=None, ge=1)


class ScopeResponse(BaseModel):
    id: int
    user_id: int
    scope_type: Literal["product", "version"]
    product_id: int
    product_version_id: int | None
    scope_key: str
    created_by: int
    created_at: datetime
    updated_at: datetime
    is_effective: bool


class ScopeSummaryResponse(BaseModel):
    is_global: bool
    scopes: list[ScopeResponse]
    effective_product_ids: list[int]
    effective_version_ids: list[int]
